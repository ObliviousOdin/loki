# update-job.ps1 -- the Win32 job/process helper windows.ps1 runs every
# hermes step through (dot-sourced after the marker claim, never before it:
# Add-Type is not allowed in the claim path). StartAssigned creates the step
# SUSPENDED inside a private job (kill-on-close until Resume), so windows.ps1
# can publish the update marker's delegate before the first instruction runs.

function Initialize-HermesUpdateJob {
    # Compile the helper once per PowerShell session (Add-Type cannot redefine a type).
    if ("HermesUpdateJob" -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using Microsoft.Win32.SafeHandles;

public static class HermesUpdateJob {
    public sealed class StartedProcess {
        public Process Process;
        public StreamReader StandardOutput;
        public StreamReader StandardError;
        public IntPtr Job;
        public IntPtr Thread;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimitInformation {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimitInformation {
        public BasicLimitInformation Basic;
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(IntPtr job, int informationClass, ref ExtendedLimitInformation information, uint length);

    // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x2000) on, or every limit off.
    private static bool SetKillOnClose(IntPtr job, bool on) {
        ExtendedLimitInformation information = new ExtendedLimitInformation();
        information.Basic.LimitFlags = on ? 0x2000u : 0u;
        return SetInformationJobObject(job, 9, ref information, (uint)Marshal.SizeOf(typeof(ExtendedLimitInformation)));
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes {
        public int Length;
        public IntPtr SecurityDescriptor;
        public bool InheritHandle;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct StartupInfo {
        public int Size;
        public string Reserved;
        public string Desktop;
        public string Title;
        public int X;
        public int Y;
        public int XSize;
        public int YSize;
        public int XCountChars;
        public int YCountChars;
        public int FillAttribute;
        public int Flags;
        public short ShowWindow;
        public short Reserved2;
        public IntPtr Reserved2Ptr;
        public IntPtr StdInput;
        public IntPtr StdOutput;
        public IntPtr StdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInformation {
        public IntPtr Process;
        public IntPtr Thread;
        public int ProcessId;
        public int ThreadId;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicAccountingInformation {
        public long TotalUserTime;
        public long TotalKernelTime;
        public long ThisPeriodTotalUserTime;
        public long ThisPeriodTotalKernelTime;
        public uint TotalPageFaultCount;
        public uint TotalProcesses;
        public uint ActiveProcesses;
        public uint TotalTerminatedProcesses;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateJobObject(IntPtr attributes, string name);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CreatePipe(out IntPtr read, out IntPtr write, ref SecurityAttributes attributes, int size);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetHandleInformation(IntPtr handle, int mask, int flags);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateFile(
        string fileName, uint desiredAccess, uint shareMode, ref SecurityAttributes attributes,
        uint creationDisposition, uint flagsAndAttributes, IntPtr templateFile
    );

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcess(
        string applicationName, StringBuilder commandLine,
        IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles,
        int creationFlags, IntPtr environment, string currentDirectory,
        ref StartupInfo startupInfo, out ProcessInformation processInformation
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint ResumeThread(IntPtr thread);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool TerminateProcess(IntPtr process, uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool TerminateJobObject(IntPtr job, uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool QueryInformationJobObject(
        IntPtr job,
        int informationClass,
        out BasicAccountingInformation information,
        uint informationLength,
        IntPtr returnLength
    );

    [DllImport("kernel32.dll", EntryPoint = "QueryInformationJobObject", SetLastError = true)]
    private static extern bool QueryInformationJobObjectRaw(
        IntPtr job, int informationClass, IntPtr information, uint informationLength, IntPtr returnLength);

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    [StructLayout(LayoutKind.Sequential)]
    private struct CompletionAssociation {
        public IntPtr Key, Port;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct FileTime { public uint Low, High; }

    [DllImport("kernel32.dll", EntryPoint = "SetInformationJobObject", SetLastError = true)]
    private static extern bool SetCompletionPort(IntPtr job, int kind, ref CompletionAssociation association, uint size);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateIoCompletionPort(IntPtr file, IntPtr existing, UIntPtr key, uint concurrency);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetQueuedCompletionStatus(IntPtr port, out uint message, out UIntPtr key, out IntPtr process, uint timeout);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool PostQueuedCompletionStatus(IntPtr port, uint message, UIntPtr key, IntPtr process);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool member);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetProcessTimes(IntPtr process, out FileTime creation, out FileTime exit, out FileTime kernel, out FileTime user);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint GetProcessId(IntPtr process);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(IntPtr handle, uint timeout);
    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool DuplicateHandle(IntPtr source, IntPtr handle, IntPtr target, out IntPtr duplicate, uint access, bool inherit, uint options);

    private static readonly object LedgersLock = new object();
    private static readonly Dictionary<IntPtr, LifetimeLedger> Ledgers = new Dictionary<IntPtr, LifetimeLedger>();

    private sealed class LifetimeLedger {
        private readonly object gate = new object();
        private readonly Dictionary<string, IntPtr> handles = new Dictionary<string, IntPtr>();
        private readonly AutoResetEvent changed = new AutoResetEvent(false);
        private readonly ManualResetEvent stop = new ManualResetEvent(false);
        private IntPtr queryJob, port;
        private Thread consumer;
        private volatile bool stopping;
        private bool uncertain;
        private Stopwatch cancellationClock;
        private int cancellationTimeout;

        public LifetimeLedger(IntPtr job) {
            try {
                if (!DuplicateHandle(GetCurrentProcess(), job, GetCurrentProcess(), out queryJob, 4, false, 0))
                    throw new Win32Exception();
                port = CreateIoCompletionPort(new IntPtr(-1), IntPtr.Zero, UIntPtr.Zero, 1);
                if (port == IntPtr.Zero) throw new Win32Exception();
                CompletionAssociation association = new CompletionAssociation { Key = job, Port = port };
                if (!SetCompletionPort(job, 7, ref association, (uint)Marshal.SizeOf(typeof(CompletionAssociation))))
                    throw new Win32Exception();
                consumer = new Thread(Consume);
                consumer.IsBackground = true;
                consumer.Start();
            } catch {
                CompletionAssociation empty = new CompletionAssociation();
                SetCompletionPort(job, 7, ref empty, (uint)Marshal.SizeOf(typeof(CompletionAssociation)));
                if (port != IntPtr.Zero) CloseHandle(port);
                if (queryJob != IntPtr.Zero) CloseHandle(queryJob);
                changed.Dispose(); stop.Dispose();
                throw;
            }
        }

        private bool Enter(Stopwatch clock, int timeoutMs) {
            if (clock != null) return Monitor.TryEnter(gate, Remaining(clock, timeoutMs));
            Monitor.Enter(gate);
            return true;
        }

        private bool Uncertain(Stopwatch clock = null, int timeoutMs = 0) {
            if (Enter(clock, timeoutMs)) {
                try { uncertain = true; changed.Set(); }
                finally { Monitor.Exit(gate); }
            }
            return false;
        }

        private bool Keep(IntPtr handle, uint pid, Stopwatch clock = null, int timeoutMs = 0) {
            bool member;
            FileTime creation, exit, kernel, user;
            if (GetProcessId(handle) != pid || !IsProcessInJob(handle, queryJob, out member) || !member ||
                    !GetProcessTimes(handle, out creation, out exit, out kernel, out user)) {
                CloseHandle(handle);
                return Uncertain(clock, timeoutMs);
            }
            ulong birth = ((ulong)creation.High << 32) | creation.Low;
            string identity = pid.ToString("X8") + ":" + birth.ToString("X16");
            if (!Enter(clock, timeoutMs)) { CloseHandle(handle); return false; }
            try {
                bool retained = true;
                if (handles.ContainsKey(identity)) CloseHandle(handle);
                else if (handles.Count >= 65536) { CloseHandle(handle); uncertain = true; retained = false; }
                else handles.Add(identity, handle);
                changed.Set();
                return retained;
            } finally { Monitor.Exit(gate); }
        }

        public void PinRoot(IntPtr original, uint pid) {
            IntPtr owned;
            if (!DuplicateHandle(GetCurrentProcess(), original, GetCurrentProcess(), out owned, 0x101000, false, 0))
                throw new Win32Exception();
            if (!Keep(owned, pid)) throw new InvalidOperationException("Unable to retain the original update process identity");
        }

        private bool Pin(uint pid, Stopwatch clock = null, int timeoutMs = 0) {
            IntPtr handle = OpenProcess(0x101000, false, pid);
            return handle == IntPtr.Zero ? Uncertain(clock, timeoutMs) : Keep(handle, pid, clock, timeoutMs);
        }

        private void Consume() {
            try {
                while (!stopping) {
                    uint message; UIntPtr key; IntPtr process;
                    // The short port wait bounds shutdown even if its wake packet fails;
                    // cancellation itself waits on signals, never this interval.
                    if (!GetQueuedCompletionStatus(port, out message, out key, out process, 100)) {
                        if (Marshal.GetLastWin32Error() == 258) continue;
                        throw new Win32Exception();
                    }
                    if (stopping) break;
                    if (message == 6) {
                        long pid = process.ToInt64();
                        if (pid <= 0 || pid > uint.MaxValue) Uncertain();
                        else Pin((uint)pid);
                    }
                    // Accounting hints wake a recheck; none proves completion.
                    else if (message == 4 || message == 7 || message == 8) changed.Set();
                }
            } catch {
                Uncertain();
                // Only Close may release handles, after the cancellation caller
                // has finished its waits. A failed observer cannot race that wait.
                while (!stopping) stop.WaitOne(100);
            } finally {
                lock (gate) {
                    foreach (IntPtr handle in handles.Values) CloseHandle(handle);
                    handles.Clear();
                    CloseHandle(queryJob);
                    CloseHandle(port);
                    changed.Dispose(); stop.Dispose();
                }
            }
        }

        public void BeginCancellation(Stopwatch clock, int timeoutMs) {
            cancellationClock = clock;
            cancellationTimeout = timeoutMs;
        }

        public bool CaptureCurrent(IntPtr job, Stopwatch clock, int timeoutMs) {
            int[] members;
            if (!TryProcessIds(job, out members, clock, timeoutMs)) return Uncertain(clock, timeoutMs);
            foreach (int pid in members) {
                if (Remaining(clock, timeoutMs) == 0 || !Pin(unchecked((uint)pid), clock, timeoutMs)) return false;
            }
            return true;
        }

        public bool Snapshot(Stopwatch clock, int timeoutMs, out IntPtr[] result, out bool certain) {
            result = new IntPtr[0]; certain = false;
            if (!Enter(clock, timeoutMs)) return false;
            try {
                certain = !uncertain;
                result = new IntPtr[handles.Count];
                handles.Values.CopyTo(result, 0);
                return true;
            } finally { Monitor.Exit(gate); }
        }

        public void WaitForChange(int milliseconds) { changed.WaitOne(milliseconds); }

        public void Close(IntPtr job) {
            Stopwatch clock = cancellationClock ?? Stopwatch.StartNew();
            int timeoutMs = cancellationClock == null ? 2000 : cancellationTimeout;
            bool detached;
            if (Enter(clock, timeoutMs)) {
                try {
                    CompletionAssociation empty = new CompletionAssociation();
                    detached = SetCompletionPort(job, 7, ref empty, (uint)Marshal.SizeOf(typeof(CompletionAssociation)));
                    stopping = true;
                    stop.Set();
                    PostQueuedCompletionStatus(port, 0, UIntPtr.Zero, IntPtr.Zero);
                } finally { Monitor.Exit(gate); }
            } else {
                CompletionAssociation empty = new CompletionAssociation();
                detached = SetCompletionPort(job, 7, ref empty, (uint)Marshal.SizeOf(typeof(CompletionAssociation)));
                // Do not touch port/events after this flag: the consumer may
                // already be disposing them. Its bounded port wait sees it.
                stopping = true;
            }
            int remaining = Remaining(clock, timeoutMs);
            bool joined = remaining > 0 && consumer.Join(remaining);
            // Exhausted cancellation leaves finalization with the consumer;
            // it owns a query-job duplicate and never kills successful services.
            if (!joined && cancellationClock == null) throw new InvalidOperationException("Update process observer did not stop");
            if (!detached) throw new InvalidOperationException("Unable to detach update process observer");
        }
    }

    private static int Remaining(Stopwatch clock, int timeoutMs) {
        long elapsed = clock.ElapsedMilliseconds;
        return elapsed >= timeoutMs ? 0 : timeoutMs - (int)elapsed;
    }

    private static bool TryProcessIds(IntPtr job, out int[] ids, Stopwatch clock = null, int timeoutMs = 0) {
        ids = new int[0];
        if (job == IntPtr.Zero) return false;
        for (int capacity = 16; capacity <= 65536; capacity *= 2) {
            if (clock != null && Remaining(clock, timeoutMs) == 0) return false;
            int size = checked(8 + IntPtr.Size * capacity);
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try {
                if (!QueryInformationJobObjectRaw(job, 3, buffer, (uint)size, IntPtr.Zero)) {
                    if (Marshal.GetLastWin32Error() == 234) continue;
                    return false;
                }
                int assigned = Marshal.ReadInt32(buffer, 0), count = Marshal.ReadInt32(buffer, 4);
                if (assigned < 0 || count < 0 || count > capacity) return false;
                if (count < assigned) continue;
                ids = new int[count];
                for (int i = 0; i < count; i++) {
                    long pid = Marshal.ReadIntPtr(buffer, 8 + i * IntPtr.Size).ToInt64();
                    if (pid <= 0 || pid > int.MaxValue) return false;
                    ids[i] = (int)pid;
                }
                return true;
            } finally { Marshal.FreeHGlobal(buffer); }
        }
        return false;
    }

    // Diagnostic delegates only; cancellation never treats a failed query as empty.
    public static int[] ProcessIds(IntPtr job) {
        int[] ids;
        return TryProcessIds(job, out ids) ? ids : new int[0];
    }

    // CPU time plus I/O bytes the job's processes have spent so far
    // (JobObjectBasicAndIoAccountingInformation: 48-byte basic accounting,
    // then IO_COUNTERS). Any change is progress; -1 when unavailable.
    public static long Activity(IntPtr job) {
        if (job == IntPtr.Zero) return -1;
        const int size = 96;
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try {
            if (!QueryInformationJobObjectRaw(job, 8, buffer, size, IntPtr.Zero)) return -1;
            return Marshal.ReadInt64(buffer, 0) + Marshal.ReadInt64(buffer, 8)
                + Marshal.ReadInt64(buffer, 72) + Marshal.ReadInt64(buffer, 80) + Marshal.ReadInt64(buffer, 88);
        } finally { Marshal.FreeHGlobal(buffer); }
    }

    public static StartedProcess StartAssigned(string executable, string arguments) {
        IntPtr job = IntPtr.Zero;
        IntPtr outRead = IntPtr.Zero, outWrite = IntPtr.Zero;
        IntPtr errRead = IntPtr.Zero, errWrite = IntPtr.Zero;
        IntPtr nullInput = new IntPtr(-1);
        ProcessInformation pi = new ProcessInformation();
        try {
            job = CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero) throw new InvalidOperationException("CreateJobObject failed");
            // Until Resume: should this script die while the child is still
            // suspended, closing the job kills it before it ran anything.
            if (!SetKillOnClose(job, true)) throw new InvalidOperationException("SetInformationJobObject failed");
            LifetimeLedger ledger = new LifetimeLedger(job);
            lock (LedgersLock) { Ledgers.Add(job, ledger); }
            SecurityAttributes sa = new SecurityAttributes();
            sa.Length = Marshal.SizeOf(typeof(SecurityAttributes));
            sa.InheritHandle = true;
            if (!CreatePipe(out outRead, out outWrite, ref sa, 0) ||
                !CreatePipe(out errRead, out errWrite, ref sa, 0))
                throw new InvalidOperationException("CreatePipe failed");
            if (!SetHandleInformation(outRead, 1, 0) || !SetHandleInformation(errRead, 1, 0))
                throw new InvalidOperationException("SetHandleInformation failed");
            // Steps read NUL, never the hand-off console. A step that sees a
            // console asks its question into the captured stdout, where the
            // user cannot see it, and waits for an answer that never comes.
            nullInput = CreateFile("NUL", 0x80000000, 0x00000003, ref sa, 3, 0, IntPtr.Zero);
            if (nullInput == new IntPtr(-1))
                throw new InvalidOperationException("CreateFile(NUL) failed");

            StartupInfo si = new StartupInfo();
            si.Size = Marshal.SizeOf(typeof(StartupInfo));
            si.Flags = 0x00000100; // STARTF_USESTDHANDLES
            si.StdInput = nullInput;
            si.StdOutput = outWrite;
            si.StdError = errWrite;
            StringBuilder commandLine = new StringBuilder("\"" + executable + "\" " + arguments);
            if (!CreateProcess(executable, commandLine, IntPtr.Zero, IntPtr.Zero, true,
                    0x00000004 | 0x08000000, IntPtr.Zero, null, ref si, out pi))
                throw new InvalidOperationException("CreateProcess failed");
            if (!AssignProcessToJobObject(job, pi.Process)) {
                TerminateProcess(pi.Process, 1);
                throw new InvalidOperationException("AssignProcessToJobObject failed");
            }

            ledger.PinRoot(pi.Process, (uint)pi.ProcessId);
            Process process = Process.GetProcessById(pi.ProcessId);
            // Force Process to open its own stable query handle before the raw
            // CreateProcess handle is closed; PS 5.1 otherwise reports a null
            // ExitCode after fast children have already disappeared.
            IntPtr stableProcessHandle = process.Handle;
            StreamReader stdout = new StreamReader(new FileStream(
                new SafeFileHandle(outRead, true), FileAccess.Read, 4096, false), Encoding.UTF8);
            StreamReader stderr = new StreamReader(new FileStream(
                new SafeFileHandle(errRead, true), FileAccess.Read, 4096, false), Encoding.UTF8);
            outRead = IntPtr.Zero;
            errRead = IntPtr.Zero;
            CloseHandle(outWrite); outWrite = IntPtr.Zero;
            CloseHandle(errWrite); errWrite = IntPtr.Zero;
            // Still suspended: the caller publishes the marker delegate, then Resume().
            StartedProcess started = new StartedProcess { Process = process, StandardOutput = stdout, StandardError = stderr, Job = job, Thread = pi.Thread };
            pi.Thread = IntPtr.Zero;
            return started;
        } catch (Exception failure) {
            if (pi.Process != IntPtr.Zero) TerminateProcess(pi.Process, 1);
            if (job != IntPtr.Zero) CloseAfterFailure(job, failure);
            throw;
        } finally {
            if (pi.Thread != IntPtr.Zero) CloseHandle(pi.Thread);
            if (pi.Process != IntPtr.Zero) CloseHandle(pi.Process);
            if (outRead != IntPtr.Zero) CloseHandle(outRead);
            if (outWrite != IntPtr.Zero) CloseHandle(outWrite);
            if (errRead != IntPtr.Zero) CloseHandle(errRead);
            if (errWrite != IntPtr.Zero) CloseHandle(errWrite);
            if (nullInput != new IntPtr(-1)) CloseHandle(nullInput);
        }
    }

    public static void Resume(StartedProcess started) {
        // Detached services a successful step starts must outlive the job
        // handle: drop kill-on-close before the first instruction runs.
        try {
            if (!SetKillOnClose(started.Job, false)) {
                TerminateJobObject(started.Job, 1);
                throw new InvalidOperationException("SetInformationJobObject failed");
            }
            if (ResumeThread(started.Thread) == 0xffffffff) {
                TerminateJobObject(started.Job, 1);
                throw new InvalidOperationException("ResumeThread failed");
            }
        } catch (Exception failure) {
            IntPtr failedJob = started.Job;
            started.Job = IntPtr.Zero;
            CloseAfterFailure(failedJob, failure);
            throw;
        } finally {
            if (started.Thread != IntPtr.Zero) CloseHandle(started.Thread);
            started.Thread = IntPtr.Zero;
        }
    }

    private static void CloseAfterFailure(IntPtr job, Exception failure) {
        try { Close(job); }
        catch (Exception cleanup) { throw new AggregateException("Update process initialization and observer cleanup failed", failure, cleanup); }
    }

    public static bool TerminateAndWait(IntPtr job, uint exitCode, int timeoutMs) {
        Stopwatch clock = Stopwatch.StartNew();
        LifetimeLedger ledger;
        lock (LedgersLock) { if (!Ledgers.TryGetValue(job, out ledger)) return false; }
        ledger.BeginCancellation(clock, timeoutMs);
        bool captured = ledger.CaptureCurrent(job, clock, timeoutMs);
        if (!TerminateJobObject(job, exitCode) || !captured) return false;
        do {
            bool certain;
            IntPtr[] handles;
            if (!ledger.Snapshot(clock, timeoutMs, out handles, out certain) || !certain) return false;
            foreach (IntPtr handle in handles) {
                int remaining = Remaining(clock, timeoutMs);
                if (WaitForSingleObject(handle, (uint)remaining) != 0) return false;
            }
            BasicAccountingInformation first, last;
            if (!QueryInformationJobObject(job, 1, out first,
                    (uint)Marshal.SizeOf(typeof(BasicAccountingInformation)), IntPtr.Zero)) return false;
            IntPtr[] latest;
            if (!ledger.Snapshot(clock, timeoutMs, out latest, out certain) || !certain) return false;
            if (handles.Length == latest.Length && (uint)latest.Length == first.TotalProcesses && first.ActiveProcesses == 0) {
                if (!QueryInformationJobObject(job, 1, out last,
                        (uint)Marshal.SizeOf(typeof(BasicAccountingInformation)), IntPtr.Zero)) return false;
                IntPtr[] final;
                if (ledger.Snapshot(clock, timeoutMs, out final, out certain) && certain && final.Length == latest.Length && last.TotalProcesses == first.TotalProcesses &&
                        last.ActiveProcesses == 0 && clock.ElapsedMilliseconds <= timeoutMs) return true;
            }
            int wait = Remaining(clock, timeoutMs);
            if (wait == 0) return false;
            ledger.WaitForChange(wait);
        } while (clock.ElapsedMilliseconds <= timeoutMs);
        return false;
    }

    public static void Close(IntPtr job) {
        LifetimeLedger ledger;
        lock (LedgersLock) {
            Ledgers.TryGetValue(job, out ledger);
            Ledgers.Remove(job);
        }
        try { if (ledger != null) ledger.Close(job); }
        finally { if (job != IntPtr.Zero) CloseHandle(job); }
    }

}
'@
}

Initialize-HermesUpdateJob
