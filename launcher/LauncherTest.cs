// Tests for the launcher's decisions (where "Bent°Corner Essentials" goes, what the cleanup removes) – no start,
// no network. Build and run from launcher\ in PowerShell (build.ps1 compiles only Launcher.cs, so this file is ignored):
//   $fw = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319"
//   & "$fw\csc.exe" /nologo /target:exe /platform:x64 /main:LauncherTest /out:$env:TEMP\LauncherTest.exe `
//     "/r:$fw\System.IO.Compression.dll" /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Core.dll `
//     Launcher.cs LauncherTest.cs; & $env:TEMP\LauncherTest.exe

using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;

static class BuildInfo { public const string Id = "0.9.3.3-2610292050"; }
static class BrandInfo { public const bool LogoCard = true; public const int Corner = 1; public const float Fold = 21; public const double Tilt = -7; public const string Name = "Bent\u00B0Corner"; }

static class LauncherTest
{
    static int fails = 0;
    static void Check(string name, bool ok) { Console.WriteLine((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

    static string Hash(string dir)
    {
        using (var sha = SHA256.Create())
        {
            var parts = Directory.GetFiles(dir, "*", SearchOption.AllDirectories).OrderBy(f => f, StringComparer.Ordinal)
                .Select(f => f.Substring(dir.Length) + ":" + BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(f))));
            return string.Join("|", parts);
        }
    }

    static string WithEnv(string name, string value, Func<string> f)
    {
        string old = Environment.GetEnvironmentVariable(name);
        Environment.SetEnvironmentVariable(name, value);
        try { return f(); } finally { Environment.SetEnvironmentVariable(name, old); }
    }

    static int Main(string[] args)
    {
        string local = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BentCorner");
        // never into the real starter.log
        string realLog = Path.Combine(local, "starter.log");
        string realLogBefore = File.Exists(realLog) ? File.ReadAllText(realLog) : null;
        Launcher.LogOverride = Path.Combine(Path.GetTempPath(), "bc-launcher-test-" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".log");
        foreach (var v in new[] { "OneDrive", "OneDriveConsumer", "OneDriveCommercial" }) Environment.SetEnvironmentVariable(v, null);
        string normal = @"C:\Users\tester\Desktop\BentCorner\app";
        Func<string, bool> IsLocal = h => Launcher.EssentialsHome(h, h) == Path.Combine(local, "inst-" + Launcher.InstallKey(h));
        Check("normal path stays", Launcher.EssentialsHome(normal, normal) == normal);
        Check("normal path not cloud", Launcher.CloudName(normal) == null);
        Environment.SetEnvironmentVariable("OneDrive", @"C:\Users\tester\OneDrive");
        Check("OneDrive (env) -> local", IsLocal(@"C:\Users\tester\OneDrive\Desktop\BentCorner"));
        Check("OneDrive env does not catch other paths", Launcher.EssentialsHome(normal, normal) == normal);
        Environment.SetEnvironmentVariable("OneDrive", null);
        Check("OneDrive (name only) -> local", IsLocal(@"C:\Users\tester\OneDrive\Dokumente\BentCorner"));
        Check("OneDrive - Firma -> local", IsLocal(@"C:\Users\tester\OneDrive - Firma GmbH\Desktop\BC"));
        Environment.SetEnvironmentVariable("OneDriveCommercial", @"D:\Firmen-Cloud");
        Check("OneDriveCommercial (env, other name) -> local", IsLocal(@"D:\Firmen-Cloud\BentCorner"));
        Environment.SetEnvironmentVariable("OneDriveCommercial", null);
        Check("Dropbox -> local", IsLocal(@"D:\Dropbox\BentCorner"));
        Check("Dropbox (Firma) -> local", IsLocal(@"C:\Users\t\Dropbox (Firma)\BentCorner"));
        Check("Google My Drive -> local", IsLocal(@"G:\My Drive\BentCorner"));
        Check("Google Meine Ablage -> local", IsLocal(@"G:\Meine Ablage\BentCorner"));
        Check("iCloud Drive -> local", IsLocal(@"C:\Users\t\iCloudDrive\BentCorner"));
        Check("name: OneDrive (env)", WithEnv("OneDrive", @"C:\Users\t\OneDrive", () => Launcher.CloudName(@"C:\Users\t\OneDrive\Desktop\BC")) == "OneDrive");
        Check("name: OneDrive - Firma", Launcher.CloudName(@"C:\Users\t\OneDrive - Firma\BC") == "OneDrive");
        Check("name: Dropbox", Launcher.CloudName(@"D:\Dropbox (Firma)\BC") == "Dropbox");
        Check("name: Google Drive", Launcher.CloudName(@"G:\Meine Ablage\BC") == "Google Drive");
        Check("name: iCloud", Launcher.CloudName(@"C:\Users\t\iCloudDrive\BC") == "iCloud");
        string longp = @"C:\" + new string('x', 200) + @"\BentCorner";
        Check("too long -> local (old rule)", IsLocal(longp));
        Check("install key: case and trailing \\ don't matter", Launcher.InstallKey(@"C:\BC\App\") == Launcher.InstallKey(@"c:\bc\app"));
        Check("install key: two folders, two keys", Launcher.InstallKey(@"C:\BC\A") != Launcher.InstallKey(@"C:\BC\B"));
        Check("just under the limit stays", Launcher.EssentialsHome(@"C:\" + new string('y', 100), normal) == @"C:\" + new string('y', 100));

        // cleanup: only other version folders inside Essentials go; data next to it stays byte for byte
        string home = Path.Combine(Path.GetTempPath(), "bc-launcher-test-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        string data = Path.Combine(home, "data", "my-data", "sessions");
        Directory.CreateDirectory(data);
        var rnd = new Random(5);
        for (int i = 0; i < 30; i++) { var b = new byte[rnd.Next(10, 5000)]; rnd.NextBytes(b); File.WriteAllBytes(Path.Combine(data, "log" + i + ".json"), b); }
        File.WriteAllText(Path.Combine(home, "settings.json"), "{\"language\": \"de\"}");
        string ess = Path.Combine(home, "Bent°Corner Essentials");
        string oldv = Path.Combine(ess, "0.9.2-2610291952"), keep = Path.Combine(ess, BuildInfo.Id);
        foreach (var d in new[] { oldv, keep }) { Directory.CreateDirectory(Path.Combine(d, "_internal", "x")); File.WriteAllText(Path.Combine(d, "_internal", "x", "f.txt"), d); }
        string before = Hash(Path.Combine(home, "data")) + File.ReadAllText(Path.Combine(home, "settings.json"));
        Launcher.Cleanup(ess, BuildInfo.Id);
        string after = Hash(Path.Combine(home, "data")) + File.ReadAllText(Path.Combine(home, "settings.json"));
        Check("cleanup removes the old version", !Directory.Exists(oldv));
        Check("cleanup keeps the current version", File.Exists(Path.Combine(keep, "_internal", "x", "f.txt")));
        Check("data and settings byte-identical", before == after && before.Length > 100);
        Directory.Delete(home, true);

        // moving out of a cloud folder: once only, data untouched – and if the service brings the files back
        // ("keep"), they stay there quietly (no second attempt, no second question)
        string root = Path.Combine(Path.GetTempPath(), "bc-launcher-cloud-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        string cloudHome = Path.Combine(root, "OneDrive", "Desktop", "BentCorner");
        string cloudData = Path.Combine(cloudHome, "data", "my-data");
        Directory.CreateDirectory(cloudData);
        for (int i = 0; i < 20; i++) { var b = new byte[rnd.Next(10, 3000)]; rnd.NextBytes(b); File.WriteAllBytes(Path.Combine(cloudData, "f" + i), b); }
        File.WriteAllText(Path.Combine(cloudHome, "settings.json"), "{\"language\": \"en\"}");
        string oldEss = Path.Combine(cloudHome, "Bent°Corner Essentials");
        Action makeOld = () => { for (int i = 0; i < 12; i++) { string d = Path.Combine(oldEss, "0.9.2-2610291952", "_internal", "d" + (i % 3)); Directory.CreateDirectory(d); File.WriteAllText(Path.Combine(d, "x" + i), "old"); } };
        makeOld();
        Launcher.LocalOverride = Path.Combine(root, "local");
        Directory.CreateDirectory(Launcher.LocalOverride);
        File.WriteAllText(Path.Combine(Launcher.LocalOverride, "essentials.txt"), oldEss);
        string newEss = Path.Combine(Launcher.EssentialsHome(cloudHome, cloudHome), "Bent°Corner Essentials");
        Check("cloud data -> Essentials local (own folder per installation)", newEss == Path.Combine(Launcher.LocalOverride, "inst-" + Launcher.InstallKey(cloudHome), "Bent°Corner Essentials"));
        string dataBefore = Hash(Path.Combine(cloudHome, "data")) + File.ReadAllText(Path.Combine(cloudHome, "settings.json"));
        int n;
        string svc = Launcher.OldEssentialsCloud(newEss, cloudHome, cloudHome, out n);
        Check("first start: note shown (OneDrive, 12 files)", svc == "OneDrive" && n == 12);
        Launcher.RememberAndForgetOld(newEss, cloudHome, cloudHome);
        Check("first start: old program in the cloud removed", !Directory.Exists(oldEss));
        Check("first start: data and settings byte-identical", dataBefore == Hash(Path.Combine(cloudHome, "data")) + File.ReadAllText(Path.Combine(cloudHome, "settings.json")));
        makeOld();   // the user chose "keep": OneDrive brings the files back
        svc = Launcher.OldEssentialsCloud(newEss, cloudHome, cloudHome, out n);
        Check("next start: no note any more", svc == null);
        Launcher.RememberAndForgetOld(newEss, cloudHome, cloudHome);
        Check("next start: the kept files stay (no second deleting, no second question)", Directory.Exists(oldEss) && Directory.GetFiles(oldEss, "*", SearchOption.AllDirectories).Length == 12);
        Check("next start: data still byte-identical", dataBefore == Hash(Path.Combine(cloudHome, "data")) + File.ReadAllText(Path.Combine(cloudHome, "settings.json")));
        Launcher.LocalOverride = null;
        Directory.Delete(root, true);

        StablePath();
        CloudMoveNewLayout();
        TwoInstallations();
        TestEnvSwitches();
        Check("log went to the test file", File.Exists(Launcher.LogOverride) && File.ReadAllText(Launcher.LogOverride).Length > 0);
        Check("real starter.log untouched", (File.Exists(realLog) ? File.ReadAllText(realLog) : null) == realLogBefore);
        File.Delete(Launcher.LogOverride);
        Launcher.LogOverride = null;
        Console.WriteLine(fails == 0 ? "ALL OK" : fails + " FAILED");
        return fails;
    }
    // ---- the program at a FIXED path (Essentials\BentCorner.exe), its files in Essentials\<id>\ (since 0.9.6) ----
    static string NewEss()
    {
        string ess = Path.Combine(Path.GetTempPath(), "bc-launcher-stable-" + Guid.NewGuid().ToString("N").Substring(0, 8),
                                  "Bent°Corner Essentials");
        Directory.CreateDirectory(ess);
        return ess;
    }

    // what Extract leaves behind: the files in <id>\ (.ok last) and the small exe as BentCorner.<id>.exe
    static void FakeExtract(string ess, string id)
    {
        string d = Path.Combine(ess, id, "PySide6");
        Directory.CreateDirectory(d);
        File.WriteAllText(Path.Combine(d, "Qt6Core.dll"), "dll " + id);
        File.WriteAllText(Launcher.Staged(ess, id), "exe " + id);
        File.WriteAllText(Path.Combine(ess, id, ".ok"), id);
    }

    static string Exe(string ess) { return Path.Combine(ess, "BentCorner.exe"); }
    static string Content(string f) { return File.Exists(f) ? File.ReadAllText(f) : "(missing)"; }

    // one start of the launcher for version id: extract if needed, activate, clean up -> the exe it starts
    static string Start(string ess, string id)
    {
        if (!Launcher.Ready(ess, id)) FakeExtract(ess, id);
        string inner = Launcher.Activate(ess, id);
        Launcher.Cleanup(ess, id);
        return inner;
    }

    // a test run of the exe: BC_STARTER_LOCAL / BC_STARTER_ROAMING replace the Known Folders – without them nothing changes
    static void TestEnvSwitches()
    {
        string root = Path.Combine(Path.GetTempPath(), "bc-launcher-env-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        string realLocal = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BentCorner");
        string oldLocal = Environment.GetEnvironmentVariable("BC_STARTER_LOCAL"), oldRoaming = Environment.GetEnvironmentVariable("BC_STARTER_ROAMING");
        try
        {
            Launcher.LocalOverride = null;
            Launcher.RoamingOverride = null;
            Environment.SetEnvironmentVariable("BC_STARTER_LOCAL", null);
            Environment.SetEnvironmentVariable("BC_STARTER_ROAMING", "   ");
            Launcher.ApplyTestEnv();
            Check("env: unset/empty -> no override", Launcher.LocalOverride == null && Launcher.RoamingOverride == null);
            Check("env: unset -> real %LOCALAPPDATA%\\BentCorner", Launcher.LocalHome() == realLocal);

            string local = Path.Combine(root, "local"), roaming = Path.Combine(root, "roaming");
            string data = Path.Combine(root, "daten"), app = Path.Combine(root, "app");
            Directory.CreateDirectory(Path.Combine(roaming, "BentCorner"));
            Directory.CreateDirectory(data);
            Directory.CreateDirectory(app);
            File.WriteAllText(Path.Combine(roaming, "BentCorner", "datenordner.json"),
                              "{\"home\": \"" + data.Replace("\\", "\\\\") + "\"}");
            Environment.SetEnvironmentVariable("BC_STARTER_LOCAL", local);
            Environment.SetEnvironmentVariable("BC_STARTER_ROAMING", roaming);
            Launcher.ApplyTestEnv();
            Check("env: BC_STARTER_LOCAL -> LocalHome", Launcher.LocalHome() == Path.GetFullPath(local));
            Check("env: BC_STARTER_ROAMING -> datenordner.json from there", Launcher.DataHome(app) == data);
            Directory.Delete(data);
            Check("env: no data folder -> first start in BC_STARTER_LOCAL, not the real one", Launcher.DataHome(app) == Path.GetFullPath(local));
            Check("env: Essentials of a first start below BC_STARTER_LOCAL",
                  Launcher.EssentialsHome(Launcher.DataHome(app), app).StartsWith(Path.GetFullPath(local)));
        }
        finally
        {
            Environment.SetEnvironmentVariable("BC_STARTER_LOCAL", oldLocal);
            Environment.SetEnvironmentVariable("BC_STARTER_ROAMING", oldRoaming);
            Launcher.LocalOverride = null;
            Launcher.RoamingOverride = null;
            if (Directory.Exists(root)) Directory.Delete(root, true);
        }
    }

    static void StablePath()
    {
        Launcher.RunningOverride = exe => false;
        const string A = "0.9.6.1-2611010900", B = "0.9.6.2-2611011200";

        // first start (coming from the old layout: a version folder with its own BentCorner.exe inside)
        string ess = NewEss();
        Directory.CreateDirectory(Path.Combine(ess, "0.9.5-2610310103", "_internal"));
        File.WriteAllText(Path.Combine(ess, "0.9.5-2610310103", "BentCorner.exe"), "legacy");
        Check("first start: not ready", !Launcher.Ready(ess, A));
        string inner = Start(ess, A);
        Check("first start: starts the fixed path", inner == Exe(ess) && Content(Exe(ess)) == "exe " + A);
        Check("first start: current.txt = A", Launcher.Current(ess) == A);
        Check("first start: nothing left staged", !File.Exists(Launcher.Staged(ess, A)));
        Check("first start: old-layout folder removed", !Directory.Exists(Path.Combine(ess, "0.9.5-2610310103")));
        Check("first start: now ready (next start without unpacking)", Launcher.Ready(ess, A));
        Check("same version again: the fixed path, nothing changes", Start(ess, A) == Exe(ess) && Content(Exe(ess)) == "exe " + A);

        // update, the old version not running
        inner = Start(ess, B);
        Check("update: the same fixed path", inner == Exe(ess) && Content(Exe(ess)) == "exe " + B);
        Check("update: current.txt = B", Launcher.Current(ess) == B);
        Check("update: old version's files gone", !Directory.Exists(Path.Combine(ess, A)));
        Check("update: old exe gone", Directory.GetFiles(ess, "BentCorner.*.exe").Length == 0);
        Check("update: new files there", File.Exists(Path.Combine(ess, B, "PySide6", "Qt6Core.dll")));

        // rollback: the older launcher (A) runs again
        inner = Start(ess, A);
        Check("rollback: A at the fixed path again", inner == Exe(ess) && Content(Exe(ess)) == "exe " + A && Launcher.Current(ess) == A);
        Check("rollback: B cleaned up", !Directory.Exists(Path.Combine(ess, B)));
        Directory.Delete(Path.GetDirectoryName(ess), true);

        // update while the old version is still running: no swap now – the new one starts once directly
        ess = NewEss();
        Start(ess, A);
        Launcher.RunningOverride = exe => string.Equals(exe, Exe(ess), StringComparison.OrdinalIgnoreCase);
        inner = Start(ess, B);
        Check("running old: the new one starts directly", inner == Launcher.Staged(ess, B));
        Check("running old: the fixed exe untouched (still A)", Content(Exe(ess)) == "exe " + A && Launcher.Current(ess) == A);
        Check("running old: A's files kept", File.Exists(Path.Combine(ess, A, "PySide6", "Qt6Core.dll")));
        Check("running old: B's files and exe kept", File.Exists(Path.Combine(ess, B, ".ok")) && File.Exists(Launcher.Staged(ess, B)));
        Launcher.RunningOverride = exe => false;   // closed meanwhile: the next start swaps
        Check("next start: ready without unpacking", Launcher.Ready(ess, B));
        inner = Start(ess, B);
        Check("next start: B at the fixed path", inner == Exe(ess) && Content(Exe(ess)) == "exe " + B && Launcher.Current(ess) == B);
        Check("next start: A cleaned up", !Directory.Exists(Path.Combine(ess, A)) && Directory.GetFiles(ess, "BentCorner.*.exe").Length == 0);
        Directory.Delete(Path.GetDirectoryName(ess), true);

        // renaming fails (e.g. the virus scanner holds the new exe): fall back to starting it directly
        ess = NewEss();
        Start(ess, A);
        FakeExtract(ess, B);
        using (new FileStream(Launcher.Staged(ess, B), FileMode.Open, FileAccess.Read, FileShare.Read))   // no rename
        {
            inner = Launcher.Activate(ess, B);
            Check("rename fails (new exe): starts it directly", inner == Launcher.Staged(ess, B));
            Check("rename fails (new exe): the fixed exe still A", Content(Exe(ess)) == "exe " + A && Launcher.Current(ess) == A);
            Check("rename fails (new exe): nothing parked left behind", Directory.GetFiles(ess, "BentCorner.old-*.exe").Length == 0);
        }
        using (new FileStream(Exe(ess), FileMode.Open, FileAccess.Read, FileShare.Read))   // the fixed exe held
        {
            inner = Launcher.Activate(ess, B);
            Check("rename fails (fixed exe): starts the new one directly", inner == Launcher.Staged(ess, B));
            Check("rename fails (fixed exe): A still in place", Content(Exe(ess)) == "exe " + A);
        }
        inner = Start(ess, B);
        Check("free again: the next start swaps", inner == Exe(ess) && Content(Exe(ess)) == "exe " + B && Launcher.Current(ess) == B);
        Directory.Delete(Path.GetDirectoryName(ess), true);

        // cleanup leaves what still runs: a parked old exe that can't be deleted keeps its folder
        ess = NewEss();
        Start(ess, A);
        FakeExtract(ess, B);
        Launcher.Activate(ess, B);   // A parked as BentCorner.old-A.exe
        string parked = Path.Combine(ess, "BentCorner.old-" + A + ".exe");
        Check("parked: old exe renamed", File.Exists(parked) && Content(parked) == "exe " + A);
        using (new FileStream(parked, FileMode.Open, FileAccess.Read, FileShare.Read))   // "running": can't be deleted
        {
            Launcher.Cleanup(ess, B);
            Check("cleanup: running old exe and its files stay", File.Exists(parked) && Directory.Exists(Path.Combine(ess, A)));
        }
        Launcher.Cleanup(ess, B);
        Check("cleanup: gone once it has ended", !File.Exists(parked) && !Directory.Exists(Path.Combine(ess, A)));
        // old layout, still running: its exe inside the folder can't be deleted -> the folder stays
        string legacy = Path.Combine(ess, "0.9.5-2610310103");
        Directory.CreateDirectory(Path.Combine(legacy, "_internal"));
        File.WriteAllText(Path.Combine(legacy, "BentCorner.exe"), "legacy");
        File.WriteAllText(Path.Combine(legacy, "_internal", "x.dll"), "x");
        using (new FileStream(Path.Combine(legacy, "BentCorner.exe"), FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            Launcher.Cleanup(ess, B);
            Check("cleanup: running old-layout version stays complete", File.Exists(Path.Combine(legacy, "_internal", "x.dll")));
        }
        Launcher.Cleanup(ess, B);
        Check("cleanup: old-layout version gone once ended", !Directory.Exists(legacy));
        Check("cleanup: the current version untouched", Content(Exe(ess)) == "exe " + B && File.Exists(Path.Combine(ess, B, ".ok")));
        Directory.Delete(Path.GetDirectoryName(ess), true);
        Launcher.RunningOverride = null;
    }

    // data in a cloud folder: Essentials (new layout) moves to %LOCALAPPDATA% – once, the data stays byte for byte
    static void CloudMoveNewLayout()
    {
        Launcher.RunningOverride = exe => false;
        const string A = "0.9.6.1-2611010900", B = "0.9.6.2-2611011200";
        string root = Path.Combine(Path.GetTempPath(), "bc-launcher-cloud2-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        string cloudHome = Path.Combine(root, "OneDrive", "Desktop", "BentCorner");
        Directory.CreateDirectory(Path.Combine(cloudHome, "data", "my-data"));
        File.WriteAllText(Path.Combine(cloudHome, "data", "my-data", "collection.json"), "{\"items\": [1, 2, 3]}");
        File.WriteAllText(Path.Combine(cloudHome, "settings.json"), "{\"language\": \"de\"}");
        string oldEss = Path.Combine(cloudHome, "Bent°Corner Essentials");
        Directory.CreateDirectory(oldEss);
        FakeExtract(oldEss, A);
        Launcher.Activate(oldEss, A);   // an earlier version lived in the cloud folder, new layout
        Launcher.LocalOverride = Path.Combine(root, "local");
        Directory.CreateDirectory(Launcher.LocalOverride);
        File.WriteAllText(Path.Combine(Launcher.LocalOverride, "essentials.txt"), oldEss);
        string dataBefore = Hash(Path.Combine(cloudHome, "data")) + File.ReadAllText(Path.Combine(cloudHome, "settings.json"));
        string ess = Path.Combine(Launcher.EssentialsHome(cloudHome, cloudHome), "Bent°Corner Essentials");
        Check("cloud (new layout): Essentials local", ess == Path.Combine(Launcher.LocalOverride, "inst-" + Launcher.InstallKey(cloudHome), "Bent°Corner Essentials"));
        Directory.CreateDirectory(ess);
        int n;
        Check("cloud (new layout): note shown", Launcher.OldEssentialsCloud(ess, cloudHome, cloudHome, out n) == "OneDrive" && n > 0);
        string inner = Start(ess, B);
        Launcher.RememberAndForgetOld(ess, cloudHome, cloudHome);
        Check("cloud (new layout): starts the fixed local path", inner == Exe(ess) && Content(Exe(ess)) == "exe " + B);
        Check("cloud (new layout): old program in the cloud removed", !Directory.Exists(oldEss));
        Check("cloud (new layout): data byte-identical", dataBefore == Hash(Path.Combine(cloudHome, "data")) + File.ReadAllText(Path.Combine(cloudHome, "settings.json")));
        Launcher.LocalOverride = null;
        Launcher.RunningOverride = null;
        Directory.Delete(root, true);
    }
    // ---- two installations side by side (a stick + the PC, a portable copy): neither removes the other's program ----
    // what the launcher's Main does with Essentials, for the installation in appDir (data next to it)
    static string Launch(string appDir, string id)
    {
        string home = appDir;
        string ess = Path.Combine(Launcher.EssentialsHome(home, appDir), "Bent°Corner Essentials");
        Launcher.MarkOwner(ess, appDir);
        int n;
        Launcher.OldEssentialsCloud(ess, appDir, home, out n);
        string inner = Start(ess, id);
        Launcher.RememberAndForgetOld(ess, appDir, home);
        return inner;
    }

    static bool Intact(string ess, string id)
    {
        return Content(Exe(ess)) == "exe " + id && File.Exists(Path.Combine(ess, id, "PySide6", "Qt6Core.dll"));
    }

    static void TwoInstallations()
    {
        Launcher.RunningOverride = exe => false;
        const string A = "0.9.6.1-2611010900", B = "0.9.6.2-2611011200";
        string root = Path.Combine(Path.GetTempPath(), "bc-launcher-two-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Launcher.LocalOverride = Path.Combine(root, "local");
        Directory.CreateDirectory(Launcher.LocalOverride);
        string appA = Path.Combine(root, "A"), appB = Path.Combine(root, "B");
        Directory.CreateDirectory(appA);
        Directory.CreateDirectory(appB);
        string essA = Path.Combine(appA, "Bent°Corner Essentials"), essB = Path.Combine(appB, "Bent°Corner Essentials");

        // both started in turn, also with different versions: each keeps its own
        Launch(appA, A);
        Launch(appB, B);
        Check("two installations: B did not remove A", Intact(essA, A));
        Launch(appA, A);
        Check("two installations: A did not remove B", Intact(essB, B));
        Launch(appB, B);
        Launch(appA, B);   // A updated
        Launch(appB, A);   // B rolled back
        Check("two installations, alternating with updates: both complete", Intact(essA, B) && Intact(essB, A));
        Check("two installations: each Essentials marked with its own folder",
              File.ReadAllText(Path.Combine(essA, "installation.txt")).Trim() == Path.GetFullPath(appA)
              && File.ReadAllText(Path.Combine(essB, "installation.txt")).Trim() == Path.GetFullPath(appB));
        Check("two installations: one note each", Directory.GetFiles(Launcher.LocalOverride, "essentials-*.txt").Length == 2);

        // the incident of 31.10.: the old note (one for all, bis 0.9.6) points at A's Essentials, then a new
        // installation C starts for the first time -> A's stays
        string appC = Path.Combine(root, "C");
        Directory.CreateDirectory(appC);
        File.WriteAllText(Path.Combine(Launcher.LocalOverride, "essentials.txt"), essA);
        Launch(appC, A);
        Check("old shared note -> A: C leaves A alone", Intact(essA, B));
        // an older A without marker (before 0.9.6): not next to C's data -> not C's, stays
        File.Delete(Path.Combine(essA, "installation.txt"));
        File.Delete(Directory.GetFiles(Launcher.LocalOverride, "essentials-" + Launcher.InstallKey(appC) + ".txt")[0]);
        Launch(appC, A);
        Check("old shared note -> unmarked folder elsewhere: stays", Intact(essA, B));
        Check("Mine: someone else's marker -> no", !Launcher.Mine(essB, appA, appA));
        Check("Mine: unmarked, not next to our data -> no", !Launcher.Mine(essA, appC, appC));
        Check("Mine: unmarked, next to our data -> yes", Launcher.Mine(essA, appA, appA));
        Check("Mine: our marker -> yes", Launcher.Mine(Path.Combine(appC, "Bent°Corner Essentials"), appC, appC));
        string other = Path.Combine(root, "something", "Programme");
        Directory.CreateDirectory(other);
        File.WriteAllText(Path.Combine(other, "x.txt"), "x");
        Check("Mine: a folder with another name -> no (never deleted)", !Launcher.Mine(other, appA, appA));
        File.WriteAllText(Path.Combine(Launcher.LocalOverride, "essentials.txt"), other);
        string appD = Path.Combine(root, "D");
        Directory.CreateDirectory(appD);
        Launch(appD, A);
        Check("old shared note -> unknown folder: stays", File.Exists(Path.Combine(other, "x.txt")));

        // the old shared note pointing at OUR Essentials: taken over gently, same place -> nothing deleted
        string appE = Path.Combine(root, "E"), essE = Path.Combine(appE, "Bent°Corner Essentials");
        Directory.CreateDirectory(essE);
        FakeExtract(essE, A);
        Launcher.Activate(essE, A);
        File.WriteAllText(Path.Combine(Launcher.LocalOverride, "essentials.txt"), essE);
        Check("old shared note -> our own: taken over", Launcher.LastEssentials(appE, appE) == essE);
        Launch(appE, A);
        Check("old shared note -> our own, same place: kept", Intact(essE, A));
        Check("old shared note left as it is (older launchers still read it)", File.ReadAllText(Path.Combine(Launcher.LocalOverride, "essentials.txt")) == essE);

        // two installations with data in the cloud: each its own local Essentials, neither removes the other
        string cloudA = Path.Combine(root, "OneDrive", "A"), cloudB = Path.Combine(root, "OneDrive", "B");
        Directory.CreateDirectory(cloudA);
        Directory.CreateDirectory(cloudB);
        string lA = Path.Combine(Launcher.EssentialsHome(cloudA, cloudA), "Bent°Corner Essentials");
        string lB = Path.Combine(Launcher.EssentialsHome(cloudB, cloudB), "Bent°Corner Essentials");
        Check("cloud: two installations, two local folders", lA != lB && lA.StartsWith(Launcher.LocalOverride) && lB.StartsWith(Launcher.LocalOverride));
        Launch(cloudA, A);
        Launch(cloudB, B);
        Launch(cloudA, A);
        Launch(cloudB, B);
        Check("cloud: both complete after starting in turn", Intact(lA, A) && Intact(lB, B));

        Launcher.LocalOverride = null;
        Launcher.RunningOverride = null;
        Directory.Delete(root, true);
    }
}
