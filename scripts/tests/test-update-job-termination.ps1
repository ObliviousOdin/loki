param([Parameter(Mandatory=$true)][string]$RepoRoot,
      [Parameter(Mandatory=$true)][string]$Work,
      [switch]$CompletedChild)
$ErrorActionPreference = 'Stop'

. (Join-Path $RepoRoot 'scripts/desktop-update/update-job.ps1')

Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
public static class LokiJobExitProbe {
    public sealed class OutputCapture {
        private readonly object gate = new object();
        private readonly StringBuilder tail = new StringBuilder();
        private readonly Thread worker;
        private long characters;
        private bool closing, finished;
        private string error;
        public OutputCapture(StreamReader reader) {
            worker = new Thread(() => Drain(reader));
            worker.IsBackground = true;
            worker.Start();
        }
        private void Drain(StreamReader reader) {
            try {
                char[] buffer = new char[1024];
                int count;
                while ((count = reader.Read(buffer, 0, buffer.Length)) != 0) {
                    lock (gate) {
                        characters += count;
                        tail.Append(buffer, 0, count);
                        if (tail.Length > 1024) tail.Remove(0, tail.Length - 1024);
                    }
                }
            } catch (Exception failure) {
                lock (gate) { if (!closing) error = failure.GetType().Name + ": " + failure.Message; }
            } finally { lock (gate) { finished = true; } }
        }
        public void BeforeReaderClose() { lock (gate) { closing = true; } }
        public Dictionary<string, object> Snapshot() {
            lock (gate) {
                return new Dictionary<string, object> {
                    { "characters", characters }, { "retained_tail", tail.ToString() },
                    { "finished", finished }, { "reader_closing", closing }, { "error", error }
                };
            }
        }
    }

    [StructLayout(LayoutKind.Sequential)] private struct Accounting {
        public long User, Kernel, PeriodUser, PeriodKernel;
        public uint Faults, Total, Active, Terminated;
    }
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool member);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern uint WaitForSingleObject(IntPtr handle, uint timeout);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool TerminateProcess(IntPtr handle, uint code);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool QueryInformationJobObject(IntPtr job, int kind, IntPtr buffer, uint size, IntPtr returned);
    public static bool Member(IntPtr process, IntPtr job) {
        if (job == IntPtr.Zero) throw new InvalidOperationException("An exact owned job is required");
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
        if (job == IntPtr.Zero) throw new InvalidOperationException("An exact owned job is required");
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
    private static Accounting ReadAccounting(IntPtr job) {
        if (job == IntPtr.Zero) throw new InvalidOperationException("An exact owned job is required");
        int size=Marshal.SizeOf(typeof(Accounting));
        IntPtr buffer=Marshal.AllocHGlobal(size);
        try {
            if (!QueryInformationJobObject(job,1,buffer,(uint)size,IntPtr.Zero)) throw new Win32Exception();
            return (Accounting)Marshal.PtrToStructure(buffer,typeof(Accounting));
        } finally { Marshal.FreeHGlobal(buffer); }
    }
    public static uint Active(IntPtr job) { return ReadAccounting(job).Active; }
    public static uint Total(IntPtr job) { return ReadAccounting(job).Total; }
}
'@

if (Test-Path -LiteralPath $Work) { throw 'The diagnostic work directory must be new' }
[void][IO.Directory]::CreateDirectory($Work)
$token = [Guid]::NewGuid().ToString('N')
$rootName = 'Local\loki-job-root-' + $token
$childName = 'Local\loki-job-child-' + $token
$releaseName = 'Local\loki-job-release-' + $token
$historyReadyName = 'Local\loki-job-history-ready-' + $token
$historyReleaseName = 'Local\loki-job-history-release-' + $token
$rootReady = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $rootName)
$childReady = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $childName)
$release = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $releaseName)
$historyReady = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $historyReadyName)
$historyRelease = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $historyReleaseName)
$childScript = Join-Path $Work 'owned-child.ps1'
$rootReceipt = Join-Path $Work 'root.json'
$childReceipt = Join-Path $Work 'child.json'
$historyReceipt = Join-Path $Work 'history.json'
$source = @'
param([string]$Role, [string]$Script, [string]$Work, [string]$RootReady, [string]$ChildReady, [string]$Release,
      [int]$ControllerPid, [long]$ControllerBirthTicks,
      [int]$HistoryMode, [string]$HistoryReady, [string]$HistoryRelease)
$ErrorActionPreference='Stop'
$phaseClock=[Diagnostics.Stopwatch]::StartNew()
$phase='entered'
$controller=$ownerWait=$releaseEvent=$readyEvent=$self=$null
function Record-Phase([string]$Name) {
    $script:phase=$Name
    $record=@{role=$Role;pid=$PID;phase=$Name;elapsed_ms=$phaseClock.ElapsedMilliseconds;utc_ticks=[DateTime]::UtcNow.Ticks}
    [IO.File]::WriteAllText((Join-Path $Work ($Role+'.phase.json')),($record|ConvertTo-Json -Compress))
}
function Start-OwnedChild([string]$ChildRole) {
    Record-Phase ('starting-'+$ChildRole)
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=Join-Path $PSHOME 'powershell.exe'
    $parts=@('-NoProfile','-NonInteractive','-File',$Script,
        '-Role',$ChildRole,'-Script',$Script,'-Work',$Work,'-RootReady',$RootReady,
        '-ChildReady',$ChildReady,'-Release',$Release,'-ControllerPid',[string]$ControllerPid,
        '-ControllerBirthTicks',[string]$ControllerBirthTicks,'-HistoryMode',[string]$HistoryMode,
        '-HistoryReady',$HistoryReady,'-HistoryRelease',$HistoryRelease)
    $psi.Arguments=($parts|ForEach-Object{'"{0}"' -f $_}) -join ' '
    $psi.UseShellExecute=$false
    $psi.CreateNoWindow=$true
    $descendant=[Diagnostics.Process]::Start($psi)
    $descendant.Dispose()
    Record-Phase ('started-'+$ChildRole)
}
try {
    Record-Phase 'entered'
    $controller=[Diagnostics.Process]::GetProcessById($ControllerPid)
    [void]$controller.Handle
    if($controller.StartTime.ToUniversalTime().Ticks -ne $ControllerBirthTicks) { throw 'Controller identity changed' }
    $ownerWait=[Threading.ManualResetEvent]::new($false)
    $ownerWait.SafeWaitHandle=[Microsoft.Win32.SafeHandles.SafeWaitHandle]::new($controller.Handle,$false)
    if($ownerWait.WaitOne(0)) { throw 'Controller already exited' }
    Record-Phase 'controller-pinned'
    $releaseEvent=[Threading.EventWaitHandle]::OpenExisting($(if($Role -eq 'history'){$HistoryRelease}else{$Release}))
    $readyName=if($Role -eq 'root'){$RootReady}elseif($Role -eq 'history'){$HistoryReady}else{$ChildReady}
    $readyEvent=[Threading.EventWaitHandle]::OpenExisting($readyName)
    $self=[Diagnostics.Process]::GetCurrentProcess()
    Record-Phase 'events-opened'
    if($Role -eq 'root') {
        if($HistoryMode) { Start-OwnedChild 'history' }
        Start-OwnedChild 'child'
    }
    $identity=@{pid=$PID;birth_ticks=$self.StartTime.ToUniversalTime().Ticks;role=$Role}
    [IO.File]::WriteAllText((Join-Path $Work ($Role+'.json')),($identity|ConvertTo-Json -Compress))
    Record-Phase 'identity-published'
    [void]$readyEvent.Set()
    Record-Phase 'ready-signaled'
    [void][Threading.WaitHandle]::WaitAny([Threading.WaitHandle[]]@($releaseEvent,$ownerWait))
} catch {
    $errorRecord=@{role=$Role;pid=$PID;phase=$phase;error_type=$_.Exception.GetType().Name;
        hresult=$_.Exception.HResult;message=$_.Exception.Message.Substring(0,[Math]::Min(512,$_.Exception.Message.Length));utc_ticks=[DateTime]::UtcNow.Ticks}
    [IO.File]::WriteAllText((Join-Path $Work ($Role+'.error.json')),($errorRecord|ConvertTo-Json -Compress))
    throw
} finally {
    foreach($resource in @($self,$readyEvent,$releaseEvent,$ownerWait,$controller)) {
        if($null -ne $resource) { $resource.Dispose() }
    }
}
'@
[IO.File]::WriteAllText($childScript, $source)
$tracked = @{}
$births = @{}
$started = $stdoutCapture = $stderrCapture = $readyClock = $null
$report = [ordered]@{mode=$(if($CompletedChild){'history'}else{'static'});status='incomplete';engine=$PSVersionTable.PSVersion.ToString();observations=@();cleanup_errors=@();readiness_progress=@()}

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

function Assert-RetiredJobRefused([scriptblock]$Query) {
    try {
        & $Query | Out-Null
        throw 'A retired job query unexpectedly succeeded'
    } catch {
        if ($_.Exception.InnerException -isnot [InvalidOperationException] -or
                $_.Exception.InnerException.Message -ne 'An exact owned job is required') { throw }
    }
}

function Get-ReadinessState {
    $state=[ordered]@{elapsed_ms=$(if($readyClock){$readyClock.ElapsedMilliseconds}else{$null});events=@{};roles=@()}
    foreach($item in @(@{role='root';event=$rootReady},@{role='child';event=$childReady},@{role='history';event=$historyReady})) {
        $state.events[$item.role]=$item.event.WaitOne(0)
    }
    if($started) {
        $state.root=@{pid=$started.Process.Id;birth_ticks=$births[$started.Process.Id];wait_state=[LokiJobExitProbe]::Signal($started.Process.Handle)}
        if($state.root.wait_state -eq 0) { $state.root.exit_code=$started.Process.ExitCode }
        if($started.Job -ne [IntPtr]::Zero) {
            try { $state.job=@{active=[LokiJobExitProbe]::Active($started.Job);total=[LokiJobExitProbe]::Total($started.Job);members=@([LokiJobExitProbe]::Members($started.Job))} }
            catch { $state.job_error=$_.Exception.Message }
        }
    }
    foreach($role in @('root','child','history')) {
        $files=@{role=$role}
        foreach($suffix in @('json','phase.json','error.json')) {
            $file=Join-Path $Work ($role+'.'+$suffix)
            $files[$suffix]=@{exists=[IO.File]::Exists($file)}
            if($files[$suffix].exists) {
                try {
                    if((Get-Item -LiteralPath $file).Length -gt 8192) { throw 'Owned role diagnostic exceeds its bound' }
                    $files[$suffix].record=[IO.File]::ReadAllText($file)|ConvertFrom-Json
                } catch { $files[$suffix].read_error=$_.Exception.Message }
            }
        }
        $state.roles+= $files
    }
    if($stdoutCapture) { $state.stdout=$stdoutCapture.Snapshot() }
    if($stderrCapture) { $state.stderr=$stderrCapture.Snapshot() }
    return $state
}

try {
    $powershell = Join-Path $PSHOME 'powershell.exe'
    $controller = [Diagnostics.Process]::GetCurrentProcess()
    try {
        [void]$controller.Handle
        $controllerBirth = $controller.StartTime.ToUniversalTime().Ticks
        $queries = @(
            { [LokiJobExitProbe]::Members([IntPtr]::Zero) },
            { [LokiJobExitProbe]::Member($controller.Handle,[IntPtr]::Zero) },
            { [LokiJobExitProbe]::Active([IntPtr]::Zero) },
            { [LokiJobExitProbe]::Total([IntPtr]::Zero) }
        )
        $report.retired_job_refusals = 0
        foreach ($query in $queries) {
            Assert-RetiredJobRefused $query
            $report.retired_job_refusals++
        }
    } finally { $controller.Dispose() }
    $parts = @('-NoProfile','-NonInteractive','-File',$childScript,
        '-Role','root','-Script',$childScript,'-Work',$Work,'-RootReady',$rootName,
        '-ChildReady',$childName,'-Release',$releaseName,'-ControllerPid',[string]$PID,
        '-ControllerBirthTicks',[string]$controllerBirth,'-HistoryMode',$(if($CompletedChild){'1'}else{'0'}),
        '-HistoryReady',$historyReadyName,'-HistoryRelease',$historyReleaseName)
    $arguments = ($parts | ForEach-Object { '"{0}"' -f $_ }) -join ' '
    $started = [HermesUpdateJob]::StartAssigned($powershell,$arguments)
    [void]$started.Process.Handle
    $tracked[$started.Process.Id] = $started.Process
    $births[$started.Process.Id] = $started.Process.StartTime.ToUniversalTime().Ticks
    $stdoutCapture=[LokiJobExitProbe+OutputCapture]::new($started.StandardOutput)
    $stderrCapture=[LokiJobExitProbe+OutputCapture]::new($started.StandardError)
    $report.resume_requested_utc_ticks=[DateTime]::UtcNow.Ticks
    [HermesUpdateJob]::Resume($started)
    $report.resume_returned_utc_ticks=[DateTime]::UtcNow.Ticks
    $readyClock = [Diagnostics.Stopwatch]::StartNew()
    $report.ready_clock_started_utc_ticks=[DateTime]::UtcNow.Ticks
    $readiness = @(@{role='root';event=$rootReady},@{role='child';event=$childReady})
    if ($CompletedChild) { $readiness += @{role='history';event=$historyReady} }
    foreach ($ready in $readiness) {
        $remaining = [Math]::Max(0,30000-[int]$readyClock.ElapsedMilliseconds)
        $signaled=$ready.event.WaitOne($remaining)
        $report.readiness_progress+= @{role=$ready.role;signaled=$signaled;elapsed_ms=$readyClock.ElapsedMilliseconds}
        if (-not $signaled) { throw 'Owned processes did not publish readiness' }
    }
    $report.readiness_before_cancel=Get-ReadinessState
    $identities = @((Get-Content -LiteralPath $rootReceipt -Raw | ConvertFrom-Json),
                    (Get-Content -LiteralPath $childReceipt -Raw | ConvertFrom-Json))
    $allIdentities = $identities
    if ($CompletedChild) { $allIdentities += (Get-Content -LiteralPath $historyReceipt -Raw | ConvertFrom-Json) }
    Pin-JobMembers $started.Job
    foreach ($identity in $allIdentities) {
        $member = $tracked[[int]$identity.pid]
        if (-not $member -or $member.StartTime.ToUniversalTime().Ticks -ne [long]$identity.birth_ticks) { throw 'Original owned process identity was not pinned' }
        if ([LokiJobExitProbe]::Signal($member.Handle) -ne 258) { throw 'Owned process exited before cancellation' }
    }
    if ($CompletedChild) {
        $historyIdentity = $allIdentities | Where-Object { $_.role -eq 'history' }
        $historyHandle = $tracked[[int]$historyIdentity.pid].Handle
        $historyBefore = [LokiJobExitProbe]::Signal($historyHandle)
        if ($historyBefore -ne 258) { throw 'Historical child exited before its release' }
        [void]$historyRelease.Set()
        if ([LokiJobExitProbe]::Signal($historyHandle) -eq 258) {
            $historyWait = [Threading.ManualResetEvent]::new($false)
            try {
                $historyWait.SafeWaitHandle = [Microsoft.Win32.SafeHandles.SafeWaitHandle]::new($historyHandle,$false)
                if (-not $historyWait.WaitOne(10000)) { throw 'Historical child did not complete before cancellation' }
            } finally { $historyWait.Dispose() }
        }
        $historyAfter = [LokiJobExitProbe]::Signal($historyHandle)
        if ($historyAfter -ne 0) { throw 'Historical child is not signaled' }
        $report.history = @{pid=$historyIdentity.pid;birth_ticks=$historyIdentity.birth_ticks;
            before_wait_state=$historyBefore;after_wait_state=$historyAfter;completed_before_cancellation=$true}
        foreach ($identity in $identities) {
            if ([LokiJobExitProbe]::Signal($tracked[[int]$identity.pid].Handle) -ne 258) { throw 'Current owned role exited while history completed' }
        }
    }
    # Both live roles are now birth-fenced on the release event. No fixture
    # process can create a later descendant while cancellation is observed.
    $before = @([LokiJobExitProbe]::Members($started.Job))
    foreach ($memberId in $before) {
        if (-not $tracked.ContainsKey($memberId)) { throw 'Job membership changed after pinning' }
        if (-not $CompletedChild -and [LokiJobExitProbe]::Signal($tracked[$memberId].Handle) -ne 258) { throw 'Pinned job member exited before cancellation' }
    }
    $report.before = @{identities=$identities;members=$before;active=[LokiJobExitProbe]::Active($started.Job);total=[LokiJobExitProbe]::Total($started.Job)}
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
    try { $report.readiness_before_cleanup=Get-ReadinessState }
    catch { $report.readiness_observation_error=$_.Exception.Message }
} finally {
    [void]$release.Set()
    [void]$historyRelease.Set()
    if ($started -and $started.Job -ne [IntPtr]::Zero) {
        try { Pin-JobMembers $started.Job } catch { $report.cleanup_errors += $_.Exception.Message }
    }
    foreach ($member in @($tracked.Values)) {
        try {
            [LokiJobExitProbe]::Stop($member.Handle)
            if (-not $member.WaitForExit(5000)) { throw 'Owned process did not exit during handle-bound cleanup' }
        } catch { $report.cleanup_errors += $_.Exception.Message }
    }
    if($stdoutCapture) { $stdoutCapture.BeforeReaderClose() }
    if($stderrCapture) { $stderrCapture.BeforeReaderClose() }
    if ($started) {
        foreach ($reader in @($started.StandardOutput,$started.StandardError)) {
            try { $reader.Dispose() } catch { $report.cleanup_errors += $_.Exception.Message }
        }
        try { [HermesUpdateJob]::Close($started.Job) } catch { $report.cleanup_errors += $_.Exception.Message }
    }
    $report.cleanup_observations=@()
    foreach ($member in @($tracked.Values)) {
        try { $report.cleanup_observations+= @{pid=$member.Id;wait_state=[LokiJobExitProbe]::Signal($member.Handle)} }
        catch { $report.cleanup_errors+= $_.Exception.Message }
        $member.Dispose()
    }
    $report.streams_after_cleanup=@{}
    if($stdoutCapture) { $report.streams_after_cleanup.stdout=$stdoutCapture.Snapshot() }
    if($stderrCapture) { $report.streams_after_cleanup.stderr=$stderrCapture.Snapshot() }
    $rootReady.Dispose(); $childReady.Dispose(); $release.Dispose()
    $historyReady.Dispose(); $historyRelease.Dispose()
}
if ($report.cleanup_errors.Count) { $report.status='failed' }
[IO.File]::WriteAllText((Join-Path $Work 'receipt.json'),($report | ConvertTo-Json -Depth 8))
$report | ConvertTo-Json -Depth 8 -Compress | Write-Output
if ($report.status -ne 'passed') { exit 1 }
