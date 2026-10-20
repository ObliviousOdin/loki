param([Parameter(Mandatory=$true)][string]$RepoRoot,
      [Parameter(Mandatory=$true)][string]$Work)
$ErrorActionPreference = 'Stop'

. (Join-Path $RepoRoot 'scripts/desktop-update/update-job.ps1')

Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class LokiJobExitProbe {
    [StructLayout(LayoutKind.Sequential)] private struct Accounting {
        public long User, Kernel, PeriodUser, PeriodKernel;
        public uint Faults, Total, Active, Terminated;
    }
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool member);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern uint WaitForSingleObject(IntPtr handle, uint timeout);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool TerminateProcess(IntPtr handle, uint code);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool QueryInformationJobObject(IntPtr job, int kind, IntPtr buffer, uint size, IntPtr returned);
    public static bool Member(IntPtr process, IntPtr job) {
        bool member;
        if (!IsProcessInJob(process, job, out member)) throw new Win32Exception();
        return member;
    }
    public static uint Signal(IntPtr process) {
        uint state = WaitForSingleObject(process, 0);
        if (state == 0xffffffff) throw new Win32Exception();
        return state;
    }
    public static void Stop(IntPtr process) {
        if (Signal(process) != 0 && !TerminateProcess(process, 124) && Signal(process) != 0) throw new Win32Exception();
    }
    public static int[] Members(IntPtr job) {
        for (int capacity=16; capacity<=65536; capacity*=2) {
            int size=8+IntPtr.Size*capacity;
            IntPtr buffer=Marshal.AllocHGlobal(size);
            try {
                if (!QueryInformationJobObject(job, 3, buffer, (uint)size, IntPtr.Zero)) {
                    int error=Marshal.GetLastWin32Error();
                    if (error==234) continue;
                    throw new Win32Exception(error);
                }
                int count=Marshal.ReadInt32(buffer,4);
                if (count<0 || count>capacity) throw new InvalidOperationException("Invalid job member count");
                int[] result=new int[count];
                for (int i=0;i<count;i++) result[i]=(int)Marshal.ReadIntPtr(buffer,8+i*IntPtr.Size).ToInt64();
                return result;
            } finally { Marshal.FreeHGlobal(buffer); }
        }
        throw new InvalidOperationException("Job membership exceeded the diagnostic bound");
    }
    public static uint Active(IntPtr job) {
        int size=Marshal.SizeOf(typeof(Accounting));
        IntPtr buffer=Marshal.AllocHGlobal(size);
        try {
            if (!QueryInformationJobObject(job,1,buffer,(uint)size,IntPtr.Zero)) throw new Win32Exception();
            return ((Accounting)Marshal.PtrToStructure(buffer,typeof(Accounting))).Active;
        } finally { Marshal.FreeHGlobal(buffer); }
    }
}
'@

if (Test-Path -LiteralPath $Work) { throw 'The diagnostic work directory must be new' }
[void][IO.Directory]::CreateDirectory($Work)
$token = [Guid]::NewGuid().ToString('N')
$rootName = 'Local\loki-job-root-' + $token
$childName = 'Local\loki-job-child-' + $token
$releaseName = 'Local\loki-job-release-' + $token
$rootReady = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $rootName)
$childReady = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $childName)
$release = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $releaseName)
$childScript = Join-Path $Work 'owned-child.ps1'
$rootReceipt = Join-Path $Work 'root.json'
$childReceipt = Join-Path $Work 'child.json'
$source = @'
param([string]$Role, [string]$Script, [string]$Work, [string]$RootReady, [string]$ChildReady, [string]$Release,
      [int]$ControllerPid, [long]$ControllerBirthTicks)
$ErrorActionPreference='Stop'
$controller=[Diagnostics.Process]::GetProcessById($ControllerPid)
[void]$controller.Handle
if($controller.StartTime.ToUniversalTime().Ticks -ne $ControllerBirthTicks) { throw 'Controller identity changed' }
$ownerWait=[Threading.ManualResetEvent]::new($false)
$ownerWait.SafeWaitHandle=[Microsoft.Win32.SafeHandles.SafeWaitHandle]::new($controller.Handle,$false)
if($ownerWait.WaitOne(0)) { throw 'Controller already exited' }
$releaseEvent=[Threading.EventWaitHandle]::OpenExisting($Release)
$readyName=if($Role -eq 'root'){$RootReady}else{$ChildReady}
$readyEvent=[Threading.EventWaitHandle]::OpenExisting($readyName)
$self=[Diagnostics.Process]::GetCurrentProcess()
try {
    if($Role -eq 'root') {
        $psi=New-Object Diagnostics.ProcessStartInfo
        $psi.FileName=Join-Path $PSHOME 'powershell.exe'
        $parts=@('-NoProfile','-NonInteractive','-File',$Script,
            '-Role','child','-Script',$Script,'-Work',$Work,'-RootReady',$RootReady,
            '-ChildReady',$ChildReady,'-Release',$Release,'-ControllerPid',[string]$ControllerPid,
            '-ControllerBirthTicks',[string]$ControllerBirthTicks)
        $psi.Arguments=($parts|ForEach-Object{'"{0}"' -f $_}) -join ' '
        $psi.UseShellExecute=$false
        $psi.CreateNoWindow=$true
        $descendant=[Diagnostics.Process]::Start($psi)
        $descendant.Dispose()
    }
    $identity=@{pid=$PID;birth_ticks=$self.StartTime.ToUniversalTime().Ticks;role=$Role}
    [IO.File]::WriteAllText((Join-Path $Work ($Role+'.json')),($identity|ConvertTo-Json -Compress))
    [void]$readyEvent.Set()
    [void][Threading.WaitHandle]::WaitAny([Threading.WaitHandle[]]@($releaseEvent,$ownerWait))
} finally {
    $self.Dispose()
    $readyEvent.Dispose()
    $releaseEvent.Dispose()
    $ownerWait.Dispose()
    $controller.Dispose()
}
'@
[IO.File]::WriteAllText($childScript, $source)
$tracked = @{}
$births = @{}
$started = $null
$report = [ordered]@{status='incomplete';engine=$PSVersionTable.PSVersion.ToString();observations=@();cleanup_errors=@()}

function Pin-JobMembers([IntPtr]$Job) {
    foreach ($memberId in [LokiJobExitProbe]::Members($Job)) {
        if ($tracked.ContainsKey($memberId)) { continue }
        $member = [Diagnostics.Process]::GetProcessById($memberId)
        try {
            [void]$member.Handle
            if (-not [LokiJobExitProbe]::Member($member.Handle,$Job)) { throw 'Enumerated process is outside the owned job' }
            $births[$memberId] = $member.StartTime.ToUniversalTime().Ticks
            $tracked[$memberId] = $member
        } catch { $member.Dispose(); throw }
    }
}

try {
    $powershell = Join-Path $PSHOME 'powershell.exe'
    $controllerBirth = [Diagnostics.Process]::GetCurrentProcess().StartTime.ToUniversalTime().Ticks
    $parts = @('-NoProfile','-NonInteractive','-File',$childScript,
        '-Role','root','-Script',$childScript,'-Work',$Work,'-RootReady',$rootName,
        '-ChildReady',$childName,'-Release',$releaseName,'-ControllerPid',[string]$PID,
        '-ControllerBirthTicks',[string]$controllerBirth)
    $arguments = ($parts | ForEach-Object { '"{0}"' -f $_ }) -join ' '
    $started = [HermesUpdateJob]::StartAssigned($powershell,$arguments)
    [void]$started.Process.Handle
    $tracked[$started.Process.Id] = $started.Process
    $births[$started.Process.Id] = $started.Process.StartTime.ToUniversalTime().Ticks
    [HermesUpdateJob]::Resume($started)
    $readyClock = [Diagnostics.Stopwatch]::StartNew()
    foreach ($ready in @($rootReady,$childReady)) {
        $remaining = [Math]::Max(0,30000-[int]$readyClock.ElapsedMilliseconds)
        if (-not $ready.WaitOne($remaining)) { throw 'Owned processes did not publish readiness' }
    }
    $identities = @((Get-Content -LiteralPath $rootReceipt -Raw | ConvertFrom-Json),
                    (Get-Content -LiteralPath $childReceipt -Raw | ConvertFrom-Json))
    Pin-JobMembers $started.Job
    foreach ($identity in $identities) {
        $member = $tracked[[int]$identity.pid]
        if (-not $member -or $member.StartTime.ToUniversalTime().Ticks -ne [long]$identity.birth_ticks) { throw 'Original owned process identity was not pinned' }
        if ([LokiJobExitProbe]::Signal($member.Handle) -ne 258) { throw 'Owned process exited before cancellation' }
    }
    # Both owned roles are now birth-fenced on the release event. No fixture
    # process can create a later descendant while cancellation is observed.
    $before = @([LokiJobExitProbe]::Members($started.Job))
    foreach ($memberId in $before) {
        if (-not $tracked.ContainsKey($memberId)) { throw 'Job membership changed after pinning' }
        if ([LokiJobExitProbe]::Signal($tracked[$memberId].Handle) -ne 258) { throw 'Pinned job member exited before cancellation' }
    }
    $report.before = @{identities=$identities;members=$before;active=[LokiJobExitProbe]::Active($started.Job)}
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $safe = [HermesUpdateJob]::TerminateAndWait($started.Job,124,10000)
    $clock.Stop()
    $report.helper_returned_safe = $safe
    $report.elapsed_ms = $clock.ElapsedMilliseconds
    $report.after = @{members=@([LokiJobExitProbe]::Members($started.Job));active=[LokiJobExitProbe]::Active($started.Job)}
    foreach ($memberId in $before) {
        $member = $tracked[$memberId]
        $identity = @($identities | Where-Object { [int]$_.pid -eq $memberId })
        $role = if ($identity.Count) { $identity[0].role } else { 'job-member' }
        $signal = [LokiJobExitProbe]::Signal($member.Handle)
        $legacy = Get-Process -Id $memberId -ErrorAction SilentlyContinue
        $legacyBirth = if ($legacy) { try { $legacy.StartTime.ToUniversalTime().Ticks } catch { $null } } else { $null }
        $report.observations += @{role=$role;pid=$memberId;birth_ticks=$births[$memberId];
            wait_state=$signal;has_exited=$member.HasExited;member_after=[LokiJobExitProbe]::Member($member.Handle,$started.Job);
            legacy_pid_truthy=[bool]$legacy;legacy_birth_ticks=$legacyBirth}
        if ($legacy) { $legacy.Dispose() }
    }
    if (-not $safe) { throw 'Actual helper refused quiescence within its unchanged ten-second bound' }
    if (@($report.observations | Where-Object { $_.wait_state -ne 0 -or -not $_.has_exited }).Count) { throw 'Helper returned safe before an original process handle was signaled' }
    $report.status = 'passed'
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
} finally {
    [void]$release.Set()
    if ($started) {
        try { Pin-JobMembers $started.Job } catch { $report.cleanup_errors += $_.Exception.Message }
    }
    foreach ($member in @($tracked.Values)) {
        try {
            [LokiJobExitProbe]::Stop($member.Handle)
            if (-not $member.WaitForExit(5000)) { throw 'Owned process did not exit during handle-bound cleanup' }
        } catch { $report.cleanup_errors += $_.Exception.Message }
    }
    if ($started) {
        $started.StandardOutput.Dispose()
        $started.StandardError.Dispose()
        [HermesUpdateJob]::Close($started.Job)
    }
    foreach ($member in @($tracked.Values)) { $member.Dispose() }
    $rootReady.Dispose(); $childReady.Dispose(); $release.Dispose()
}
if ($report.cleanup_errors.Count) { $report.status='failed' }
[IO.File]::WriteAllText((Join-Path $Work 'receipt.json'),($report | ConvertTo-Json -Depth 8))
$report | ConvertTo-Json -Depth 8 -Compress | Write-Output
if ($report.status -ne 'passed') { exit 1 }
