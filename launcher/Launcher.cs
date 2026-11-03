// Starter für Bent°Corner: eine einzelne .exe, die das eigentliche Programm (PyInstaller-Ordner, als Zip hinten an
// diese Datei gehängt) einmal je Version neben den Daten ablegt – Ordner „Bent°Corner Essentials“ – und es danach
// direkt von dort startet. So entpackt nicht jeder Start 200 MB in den Temp-Ordner.
//
// Aufbau von „Essentials“ (seit 0.9.6): die kleine BentCorner.exe an FESTEM Ort, ihre ~720 Dateien im Ordner mit der
// Kennung des Builds (PyInstaller --contents-directory, die exe findet ihn über den eingebauten Namen):
//   Bent°Corner Essentials\BentCorner.exe          das laufende Programm (Pfad bleibt über Updates gleich – Windows
//                                                  merkt sich das Tray-Symbol und seine Sichtbarkeit je Pfad)
//   Bent°Corner Essentials\<Kennung>\               seine Dateien (.ok zuletzt geschrieben = vollständig)
//   Bent°Corner Essentials\current.txt               zu welcher Kennung BentCorner.exe gehört
// Update: neue Kennung entpacken (+ ihre exe als BentCorner.<Kennung>.exe), dann umbenennen: BentCorner.exe ->
// BentCorner.old-<alte Kennung>.exe, BentCorner.<Kennung>.exe -> BentCorner.exe. Läuft die alte Version noch, wird
// nicht getauscht (die neue startet einmal direkt, getauscht wird beim nächsten Start); scheitert das Umbenennen,
// ebenso. Aufgeräumt wird nur, was nicht mehr läuft.
//
// Aufbau der fertigen BentCorner.exe:  [diese exe][payload.zip][8 Byte Länge][8 Byte "BCPAYLD1"]
// Gebaut von build.ps1 mit dem csc.exe, das in jedem Windows steckt (C# 5, .NET Framework 4).
//
// Datenordner wie datahome.py: Daten neben der exe (settings.json oder data\) -> dort; sonst der gemerkte Ordner aus
// %APPDATA%\BentCorner\datenordner.json; sonst (erster Start) %LOCALAPPDATA%\BentCorner.
//
// Isoliert testen (nie in Olivers echte Ordner): BC_STARTER_LOCAL=<ordner> ersetzt %LOCALAPPDATA%\BentCorner
// (starter.log, Notizen, Essentials beim ersten Start), BC_STARTER_ROAMING=<ordner> ersetzt %APPDATA% (dort
// BentCorner\datenordner.json – datahome.py liest dieselbe Variable). Ohne die Variablen ändert sich nichts.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

static class Launcher
{
    const string FOLDER = "Bent°Corner Essentials";
    const string MAGIC = "BCPAYLD1";
    public static bool En;   // Sprache der App (settings.json „language“) – Startbild auf Englisch statt Deutsch
    public static string T(string de, string en) { return En ? en : de; }

    [STAThread]
    static int Main(string[] args)
    {
        AppDomain.CurrentDomain.UnhandledException += (s, e) => Log("Absturz: " + e.ExceptionObject);
        Application.ThreadException += (s, e) => Log("Absturz (Fenster): " + e.Exception);
        ApplyTestEnv();
        string self = Process.GetCurrentProcess().MainModule.FileName;
        string appDir = Path.GetDirectoryName(self);
        bool test = Array.IndexOf(args, "--first-run-test") >= 0;
        bool tray = Array.IndexOf(args, "--tray") >= 0;
        string home = test ? LocalHome() : DataHome(appDir);
        try
        {
            string st = Path.Combine(home, "settings.json");
            if (File.Exists(st))
                En = Regex.IsMatch(File.ReadAllText(st, Encoding.UTF8), "\"language\"\\s*:\\s*\"(?!de\")[a-z]");
        }
        catch (Exception) { }
        string essentials = Path.Combine(EssentialsHome(home, appDir), FOLDER);
        MarkOwner(essentials, appDir);
        // zieht das Programm gerade aus einem Cloud-Ordner aus (alter Ort aus essentials.txt)? Dann fragt OneDrive & Co.
        // gleich einmal nach, ob die alten Programmdateien gelöscht werden dürfen – das Startbild sagt es vorher
        int oldFiles;
        string leavingCloud = OldEssentialsCloud(essentials, appDir, home, out oldFiles);   // the service's name, or null
        string unpack = T("Packe " + BrandInfo.Name + " aus …", "Unpacking " + BrandInfo.Name + " …");
        string starting = T("Starte " + BrandInfo.Name + " …", "Starting " + BrandInfo.Name + " …");
        if (leavingCloud != null)
        {
            // the action described, not a button quoted (legal: OneDrive's wording isn't documented and changes, the
            // other services ask differently); the number of files so it can be recognised in the service's question
            string svc = leavingCloud;
            string note = T("\n" + BrandInfo.Name + " zieht aus deinem Cloud-Ordner aus und räumt die alte Programmversion weg (" + oldFiles + " Dateien). Fragt " + svc + ", ob diese Elemente gelöscht werden sollen, kannst du das bestätigen – deine Sammlung und Einstellungen bleiben, wo sie sind.",
                            "\n" + BrandInfo.Name + " is moving out of your cloud folder and removing the old program version (" + oldFiles + " files). If " + svc + " asks whether to delete these items, you can confirm – your collection and settings stay where they are.");
            unpack += note;
            starting += note;
        }
        string id = BuildInfo.Id;

        Application.EnableVisualStyles();
        Splash splash = null;
        if (!Ready(essentials, id))
        {
            splash = new Splash();
            string error = null;
            var worker = new Thread(delegate ()
            {
                var sw = Stopwatch.StartNew();
                try { Extract(self, essentials, id, splash, unpack, starting); Log("entpackt in " + sw.ElapsedMilliseconds + " ms: " + Path.Combine(essentials, id)); }
                catch (Exception e) { error = e.Message; Log("Entpacken fehlgeschlagen: " + e); }
                splash.Done();
            });
            worker.IsBackground = true;
            worker.Start();
            Application.Run(splash);   // bis Done()
            if (error != null)
            {
                splash = new Splash();
                splash.Fail(T(BrandInfo.Name + " konnte nicht vorbereitet werden:\n", BrandInfo.Name + " could not be prepared:\n") + error);
                Application.Run(splash);
                return 1;
            }
        }
        string inner = Activate(essentials, id);
        Cleanup(essentials, id);
        RememberAndForgetOld(essentials, appDir, home);

        var psi = new ProcessStartInfo(inner, JoinArgs(args));
        psi.UseShellExecute = false;
        psi.WorkingDirectory = appDir;
        psi.EnvironmentVariables["BENTCORNER_EXE"] = self;
        Process child;
        try { child = Process.Start(psi); }
        catch (Exception e)
        {
            Log("Start fehlgeschlagen: " + e);
            var s = new Splash();
            s.Fail(T(BrandInfo.Name + " ließ sich nicht starten:\n", BrandInfo.Name + " could not start:\n") + e.Message);
            Application.Run(s);
            return 1;
        }
        if (tray) return 0;   // Start mit Windows: unsichtbar im Infobereich, kein Startbild

        // Startbild, bis das Fenster da ist (ein schneller Start zeigt es gar nicht erst)
        var wait = new Splash();
        wait.Status(starting, -1);
        wait.ShowAfterMs = splash == null && leavingCloud == null ? 700 : 0;
        wait.Watch(child, 60000);
        Application.Run(wait);
        return 0;
    }

    internal static string LogOverride;   // LauncherTest only: a temporary file instead of the real starter.log

    // Kurzes Protokoll (nur Zeit + was passiert) – zur Fehlersuche, wird nie groß
    static void Log(string text)
    {
        try
        {
            string f = LogOverride ?? Path.Combine(LocalHome(), "starter.log");
            Directory.CreateDirectory(Path.GetDirectoryName(f));
            if (File.Exists(f) && new FileInfo(f).Length > 200000) File.Delete(f);
            File.AppendAllText(f, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + text + Environment.NewLine,
                               Encoding.UTF8);
        }
        catch (Exception) { }
    }

    // Wo „Bent°Corner Essentials“ (die ~720 Programmdateien je Version) hinkommt: neben die Daten – außer
    // (1) der Pfad würde zu lang: Windows-Pfade dürfen (ohne Zusatzeinstellung) höchstens 260 Zeichen lang sein, die
    //     tiefsten Dateien liegen ~90 Zeichen unter dem Versionsordner;
    // (2) die Daten liegen in einem Cloud-Ordner (OneDrive, Dropbox, Google Drive, iCloud): sonst lädt jedes Update
    //     230 MB hoch, „Dateien bei Bedarf“ kann Programmdateien nur online lassen, und das Aufräumen der alten Version
    //     löst die Massenlösch-Frage von OneDrive aus. Die Daten selbst bleiben, wo sie sind.
    // Dann: ein kurzer, lokaler Ort im Benutzerprofil – EIGENER je Installation (inst-<Kennung des Programmordners>),
    // damit zwei Installationen (Stick + PC, eine portable Kopie) sich nie gegenseitig die Programmdateien wegräumen.
    internal static string EssentialsHome(string home, string appDir)
    {
        if (home.Length + FOLDER.Length + BuildInfo.Id.Length + 100 > 255 || CloudName(home) != null)
            return Path.Combine(LocalHome(), "inst-" + InstallKey(appDir));
        return home;
    }

    // Kennung einer Installation: der Ordner, in dem die BentCorner.exe (dieser Starter) liegt – kurz als Hash
    internal static string InstallKey(string appDir)
    {
        string s = Path.GetFullPath(appDir).TrimEnd('\\').ToLowerInvariant();
        ulong h = 14695981039346656037UL;   // FNV-1a, 64 bit
        foreach (char c in s) { h ^= c; h *= 1099511628211UL; }
        return h.ToString("x16");
    }

    static bool SamePath(string a, string b)
    {
        try { return string.Equals(Path.GetFullPath(a).TrimEnd('\\'), Path.GetFullPath(b).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase); }
        catch (Exception) { return false; }
    }

    const string OWNER = "installation.txt";   // in „Essentials“: der Programmordner, zu dem es gehört

    // „Essentials“ als zu dieser Installation gehörig kennzeichnen
    internal static void MarkOwner(string essentials, string appDir)
    {
        try
        {
            Directory.CreateDirectory(essentials);
            string f = Path.Combine(essentials, OWNER);
            string me = Path.GetFullPath(appDir).TrimEnd('\\');
            if (!File.Exists(f) || File.ReadAllText(f, Encoding.UTF8).Trim() != me) File.WriteAllText(f, me, Encoding.UTF8);
        }
        catch (Exception) { }
    }

    // Gehört dieses „Essentials“ zu UNSERER Installation? Nur dann darf es weggeräumt werden: es trägt unsere
    // Kennzeichnung – oder (älterer Ordner ohne Kennzeichnung) es liegt genau neben unseren Daten. Alles andere, auch
    // Unbekanntes, gehört womöglich einer anderen Installation und bleibt.
    internal static bool Mine(string dir, string appDir, string home)
    {
        try
        {
            if (Path.GetFileName(dir.TrimEnd('\\')) != FOLDER || !Directory.Exists(dir)) return false;
            string f = Path.Combine(dir, OWNER);
            if (File.Exists(f)) return SamePath(File.ReadAllText(f, Encoding.UTF8).Trim(), appDir);
            return SamePath(dir, Path.Combine(home, FOLDER));
        }
        catch (Exception) { return false; }
    }

    static string NotePath(string appDir) { return Path.Combine(LocalHome(), "essentials-" + InstallKey(appDir) + ".txt"); }

    // Wo lag „Essentials“ dieser Installation zuletzt? Die Notiz je Installation – sonst (bis 0.9.6) die alte, eine
    // für alle (essentials.txt), aber nur, wenn ihr Ort zu uns gehört.
    internal static string LastEssentials(string appDir, string home)
    {
        try
        {
            string note = NotePath(appDir);
            if (File.Exists(note)) return File.ReadAllText(note, Encoding.UTF8).Trim();
            string legacy = Path.Combine(LocalHome(), "essentials.txt");
            if (File.Exists(legacy))
            {
                string old = File.ReadAllText(legacy, Encoding.UTF8).Trim();
                if (old.Length > 0 && Mine(old, appDir, home)) return old;
            }
        }
        catch (Exception) { }
        return null;
    }

    // the cloud service a path lies in ("OneDrive", "Dropbox", "Google Drive", "iCloud") – or null
    internal static string CloudName(string path)
    {
        try
        {
            string full = Path.GetFullPath(path).TrimEnd('\\') + "\\";
            foreach (string v in new[] { "OneDrive", "OneDriveConsumer", "OneDriveCommercial" })
            {
                string root = Environment.GetEnvironmentVariable(v);
                if (!string.IsNullOrEmpty(root)
                    && full.StartsWith(Path.GetFullPath(root).TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase))
                    return "OneDrive";
            }
            foreach (string part in full.Split('\\'))
            {
                string s = part.ToLowerInvariant();
                if (s.StartsWith("onedrive")) return "OneDrive";
                if (s == "dropbox" || s.StartsWith("dropbox (")) return "Dropbox";
                if (s == "google drive" || s == "my drive" || s == "meine ablage") return "Google Drive";
                if (s == "icloud drive" || s == "iclouddrive") return "iCloud";
            }
        }
        catch (Exception) { }
        return null;
    }

    // lag „Essentials“ dieser Installation bisher woanders, und zwar in einem Cloud-Ordner? -> der Dienst (null: nein)
    // und wie viele Dateien dort liegen. Nur einmal: RememberAndForgetOld schreibt danach den neuen Ort in die Notiz –
    // holt der Dienst die Dateien zurück („behalten“), bleiben sie still liegen, keine zweite Frage.
    internal static string OldEssentialsCloud(string essentials, string appDir, string home, out int files)
    {
        files = 0;
        try
        {
            string old = LastEssentials(appDir, home);
            if (old == null || old.Length == 0 || !Mine(old, appDir, home) || SamePath(old, essentials)) return null;
            string svc = CloudName(old);
            if (svc != null)
                files = Directory.GetFiles(old, "*", SearchOption.AllDirectories).Length;
            return svc;
        }
        catch (Exception) { return null; }
    }

    // Tests: a temporary folder instead of %LOCALAPPDATA%\BentCorner / instead of %APPDATA% (LauncherTest sets them
    // directly, a test run of the exe via BC_STARTER_LOCAL / BC_STARTER_ROAMING – see ApplyTestEnv)
    internal static string LocalOverride;
    internal static string RoamingOverride;

    // Test switches from the environment; unset or empty = nothing changes (the real Known Folders)
    internal static void ApplyTestEnv()
    {
        string local = EnvDir("BC_STARTER_LOCAL"), roaming = EnvDir("BC_STARTER_ROAMING");
        if (local != null) LocalOverride = local;
        if (roaming != null) RoamingOverride = roaming;
    }

    static string EnvDir(string name)
    {
        string v = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrWhiteSpace(v) ? null : Path.GetFullPath(v.Trim());
    }

    internal static string LocalHome()
    {
        if (LocalOverride != null) return LocalOverride;
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BentCorner");
    }

    static string Roaming()
    {
        return RoamingOverride ?? Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
    }

    internal static string DataHome(string appDir)
    {
        if (File.Exists(Path.Combine(appDir, "settings.json")) || Directory.Exists(Path.Combine(appDir, "data")))
            return appDir;
        try
        {
            string cfg = Path.Combine(Roaming(), "BentCorner", "datenordner.json");
            var m = Regex.Match(File.ReadAllText(cfg, Encoding.UTF8), "\"home\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
            if (m.Success)
            {
                string p = Regex.Unescape(m.Groups[1].Value);
                if (Directory.Exists(p)) return p;
            }
        }
        catch (Exception) { }
        return LocalHome();
    }

    // Den Ort merken (je Installation); lag „Essentials“ dieser Installation vorher woanders (erster Start,
    // Datenordner verschoben, aus der Cloud ausgezogen), den alten wegräumen – nur, wenn er sicher zu uns gehört.
    internal static void RememberAndForgetOld(string essentials, string appDir, string home)
    {
        try
        {
            Directory.CreateDirectory(LocalHome());
            string old = LastEssentials(appDir, home);
            if (old != null && old.Length > 0 && !SamePath(old, essentials) && Mine(old, appDir, home))
                TryDelete(old);
            File.WriteAllText(NotePath(appDir), essentials, Encoding.UTF8);
        }
        catch (Exception) { }
    }

    const string EXE = "BentCorner.exe";

    internal static string Staged(string essentials, string id) { return Path.Combine(essentials, "BentCorner." + id + ".exe"); }

    // zu welcher Kennung die BentCorner.exe an festem Ort gehört (null: noch keine)
    internal static string Current(string essentials)
    {
        try
        {
            string f = Path.Combine(essentials, "current.txt");
            return File.Exists(f) ? File.ReadAllText(f, Encoding.UTF8).Trim() : null;
        }
        catch (Exception) { return null; }
    }

    // diese Version vollständig da (Dateien + ihre exe – entweder noch bereitgelegt oder schon an festem Ort)?
    internal static bool Ready(string essentials, string id)
    {
        if (!File.Exists(Path.Combine(essentials, id, ".ok"))) return false;
        return File.Exists(Staged(essentials, id)) || (Current(essentials) == id && File.Exists(Path.Combine(essentials, EXE)));
    }

    internal static Func<string, bool> RunningOverride;   // LauncherTest only: instead of looking at the processes

    // läuft ein Programm aus genau dieser exe?
    internal static bool Running(string exe)
    {
        if (RunningOverride != null) return RunningOverride(exe);
        try
        {
            string full = Path.GetFullPath(exe);
            foreach (var p in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(EXE)))
            {
                try { if (string.Equals(p.MainModule.FileName, full, StringComparison.OrdinalIgnoreCase)) return true; }
                catch (Exception) { }
            }
        }
        catch (Exception) { }
        return false;
    }

    // Die Version id an den festen Ort bringen -> die exe, die gestartet wird: BentCorner.exe (fester Pfad) – oder, wenn
    // die alte noch läuft oder das Umbenennen scheitert, einmal direkt die bereitgelegte BentCorner.<id>.exe (das
    // Tray-Symbol landet dann dieses eine Mal im Überlauf; getauscht wird beim nächsten Start).
    internal static string Activate(string essentials, string id)
    {
        string stable = Path.Combine(essentials, EXE), staged = Staged(essentials, id);
        string cur = Current(essentials);
        if (cur == id && File.Exists(stable)) return stable;
        if (!File.Exists(staged)) return stable;   // nichts bereitgelegt (sollte nach Ready nicht vorkommen)
        if (File.Exists(stable) && Running(stable))
        {
            Log("alte Version läuft noch – starte " + Path.GetFileName(staged) + " direkt, getauscht wird beim nächsten Start");
            return staged;
        }
        string parked = null;
        try
        {
            if (File.Exists(stable))
            {
                parked = Path.Combine(essentials, "BentCorner.old-" + (string.IsNullOrEmpty(cur) ? "unbekannt" : cur) + ".exe");
                if (File.Exists(parked)) File.Delete(parked);
                File.Move(stable, parked);
            }
            File.Move(staged, stable);
            File.WriteAllText(Path.Combine(essentials, "current.txt"), id, Encoding.UTF8);
            return stable;
        }
        catch (Exception e)
        {
            Log("Umbenennen fehlgeschlagen (" + e.Message + ") – starte " + Path.GetFileName(staged) + " direkt");
            try { if (parked != null && !File.Exists(stable) && File.Exists(parked)) File.Move(parked, stable); }
            catch (Exception) { }
            return File.Exists(staged) ? staged : stable;
        }
    }

    // Alte Versionen weg – nur was nicht mehr läuft: eine exe, die sich nicht löschen lässt, läuft noch, ihr Ordner
    // bleibt dann bis zum nächsten Mal. Bleibt immer: die neue Version (keep) und die an festem Ort (current.txt).
    // Auch die Ordner des alten Aufbaus (bis 0.9.5: <Kennung>\BentCorner.exe) gehen so.
    internal static void Cleanup(string essentials, string keep)
    {
        try
        {
            string cur = Current(essentials);
            var busy = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string f in Directory.GetFiles(essentials, "BentCorner.*.exe"))
            {
                string name = Path.GetFileName(f);
                if (string.Equals(name, EXE, StringComparison.OrdinalIgnoreCase)) continue;
                string oid = name.StartsWith("BentCorner.old-", StringComparison.OrdinalIgnoreCase)
                    ? name.Substring("BentCorner.old-".Length, name.Length - "BentCorner.old-".Length - 4)
                    : name.Substring("BentCorner.".Length, name.Length - "BentCorner.".Length - 4);
                if (oid == keep) continue;   // die neue, noch nicht getauscht (alte Version lief)
                try { File.Delete(f); }
                catch (Exception) { busy.Add(oid); }   // läuft noch
            }
            foreach (string d in Directory.GetDirectories(essentials))
            {
                string oid = Path.GetFileName(d);
                if (oid == keep || oid == cur || busy.Contains(oid)) continue;
                string legacy = Path.Combine(d, EXE);   // alter Aufbau: die exe im Versionsordner
                if (File.Exists(legacy))
                {
                    try { File.Delete(legacy); }
                    catch (Exception) { continue; }   // läuft noch: nächstes Mal
                }
                TryDelete(d);
            }
        }
        catch (Exception) { }
    }

    static void TryDelete(string dir)
    {
        try { Directory.Delete(dir, true); } catch (Exception) { }   // läuft noch eine alte Version: nächstes Mal
    }

    static void Extract(string self, string essentials, string id, Splash splash, string unpack, string starting)
    {
        splash.Status(unpack, 0);
        // direkt an den Zielort (kein Umbenennen des Ordners am Ende – das verweigert Windows gern, solange der
        // Virenscanner die frischen Dateien prüft): die Dateien nach <id>\, die kleine exe als BentCorner.<id>.exe
        // daneben (an den festen Ort kommt sie erst in Activate); fertig erst mit der Markierung .ok, zuletzt geschrieben
        string target = Path.Combine(essentials, id);
        Directory.CreateDirectory(target);
        try { File.Delete(Path.Combine(target, ".ok")); } catch (Exception) { }
        using (var fs = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        {
            var tail = new byte[16];
            fs.Seek(-16, SeekOrigin.End);
            ReadFull(fs, tail, 16);
            if (Encoding.ASCII.GetString(tail, 8, 8) != MAGIC)
                throw new InvalidDataException("Programmdaten fehlen in der exe");
            long len = BitConverter.ToInt64(tail, 0);
            long start = fs.Length - 16 - len;
            using (var zip = new ZipArchive(new Slice(fs, start, len), ZipArchiveMode.Read))
            {
                long total = 0, done = 0;
                foreach (var e in zip.Entries) total += e.Length;
                var buf = new byte[1 << 16];
                foreach (var e in zip.Entries)
                {
                    string path = string.Equals(e.FullName, EXE, StringComparison.OrdinalIgnoreCase)
                        ? Staged(essentials, id) : Path.Combine(essentials, e.FullName.Replace('/', '\\'));
                    if (e.FullName.EndsWith("/")) { Directory.CreateDirectory(path); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(path));
                    using (var src = e.Open())
                    using (var dst = OpenWrite(path))
                    {
                        int n;
                        while ((n = src.Read(buf, 0, buf.Length)) > 0)
                        {
                            dst.Write(buf, 0, n);
                            done += n;
                            splash.Progress(total > 0 ? (double)done / total : 0);
                        }
                    }
                }
            }
        }
        File.WriteAllText(Path.Combine(target, ".ok"), id);
        splash.Status(starting, -1);
    }

    // Datei schreiben – hält sie gerade jemand fest (Virenscanner), kurz warten und nochmal
    static FileStream OpenWrite(string path)
    {
        for (int i = 0; ; i++)
        {
            try { return new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.Read); }
            catch (IOException) { if (i >= 20) throw; Thread.Sleep(250); }
            catch (UnauthorizedAccessException) { if (i >= 20) throw; Thread.Sleep(250); }
        }
    }

    static void ReadFull(Stream s, byte[] b, int n)
    {
        int got = 0;
        while (got < n)
        {
            int r = s.Read(b, got, n - got);
            if (r <= 0) throw new EndOfStreamException();
            got += r;
        }
    }

    static string JoinArgs(string[] args)
    {
        var sb = new StringBuilder();
        foreach (string a in args)
        {
            if (sb.Length > 0) sb.Append(' ');
            if (a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) { sb.Append(a); continue; }
            sb.Append('"');
            int slashes = 0;
            foreach (char c in a)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') { sb.Append('\\', slashes * 2 + 1); sb.Append('"'); slashes = 0; continue; }
                sb.Append('\\', slashes); slashes = 0; sb.Append(c);
            }
            sb.Append('\\', slashes * 2);
            sb.Append('"');
        }
        return sb.ToString();
    }
}

// Ausschnitt einer Datei als eigener Stream (das Zip hinten in der exe)
class Slice : Stream
{
    readonly Stream s; readonly long start, len; long pos;
    public Slice(Stream s, long start, long len) { this.s = s; this.start = start; this.len = len; }
    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return len; } }
    public override long Position { get { return pos; } set { pos = value; } }
    public override void Flush() { }
    public override int Read(byte[] buffer, int offset, int count)
    {
        if (pos >= len) return 0;
        if (count > len - pos) count = (int)(len - pos);
        s.Position = start + pos;
        int n = s.Read(buffer, offset, count);
        pos += n;
        return n;
    }
    public override long Seek(long offset, SeekOrigin origin)
    {
        if (origin == SeekOrigin.Begin) pos = offset;
        else if (origin == SeekOrigin.Current) pos += offset;
        else pos = len + offset;
        return pos;
    }
    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
}

// Startbild wie der Ladebildschirm der App (qml/components/BootShuffle.qml): ein schlichter Kartenstapel wird
// gemischt – die oberste Karte gleitet zur Seite und schiebt sich unten wieder drunter. Darunter Name und Status.
class Splash : Form
{
    string status = "", sub = "";
    double progress = -1;
    bool failed;
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    readonly Stopwatch clock = Stopwatch.StartNew();
    Process watched; int watchMs;
    public int ShowAfterMs;
    // Bent°Corner long version as an embedded PNG (2× sharp) – null if the build had none: then the text
    static readonly Image lockup = LoadLockup();

    static Image LoadLockup()
    {
        try
        {
            var s = typeof(Splash).Assembly.GetManifestResourceStream("Lockup.png");
            return s == null ? null : Image.FromStream(s);
        }
        catch { return null; }
    }

    static readonly Color BG = Color.FromArgb(11, 11, 11), CARD = Color.FromArgb(29, 29, 29),
                          LINE = Color.FromArgb(52, 52, 52), INK = Color.FromArgb(236, 236, 236),
                          MUTED = Color.FromArgb(138, 138, 138);
    double shownAt = -1;   // seconds on the clock when the splash became visible (the card starts there)

    public Splash()
    {
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(380, 320);
        BackColor = BG;
        ShowInTaskbar = true;
        Text = BrandInfo.Name;
        try { Icon = Icon.ExtractAssociatedIcon(Process.GetCurrentProcess().MainModule.FileName); } catch (Exception) { }
        DoubleBuffered = true;
        timer.Interval = 16;
        timer.Tick += delegate { Tick(); };
        timer.Start();
        MouseDown += delegate { if (failed) Close(); };
        CreateHandle();   // Fenster gleich anlegen (Close() muss auch vor dem Zeigen greifen)
    }

    protected override void SetVisibleCore(bool value)
    {
        // erst nach ShowAfterMs zeigen (schneller Start: gar nicht)
        base.SetVisibleCore(value && clock.ElapsedMilliseconds >= ShowAfterMs);
    }

    void Tick()
    {
        if (!Visible && clock.ElapsedMilliseconds >= ShowAfterMs && !IsDisposed) { base.SetVisibleCore(true); Activate(); }
        if (watched != null)
        {
            bool gone = false;
            try
            {
                watched.Refresh();
                gone = watched.HasExited || watched.MainWindowHandle != IntPtr.Zero;
            }
            catch (Exception) { gone = true; }
            if (gone || clock.ElapsedMilliseconds > watchMs) { Close(); return; }
        }
        Invalidate();
    }

    public void Watch(Process p, int ms) { watched = p; watchMs = ms; }

    public void Status(string text, double p)
    {
        status = text; progress = p;
        sub = p >= 0 ? Launcher.T("Nur beim ersten Start nach einem Update.", "Only on the first start after an update.") : "";
    }

    public void Progress(double p) { progress = p; }

    public void Done()
    {
        if (IsHandleCreated) BeginInvoke((MethodInvoker)delegate { Close(); });
        else { HandleCreated += delegate { BeginInvoke((MethodInvoker)delegate { Close(); }); }; }
    }

    public void Fail(string text)
    {
        failed = true; status = text; sub = Launcher.T("Klicken zum Schließen.", "Click to close."); progress = -1;
    }

    // ---- The Bent°Corner loading card (Oliver, 31.10.2026 – the same as qml/shaders/loadcard.frag, values of
    // labs/loading-anim): laid down from the front (large -> 1, fading in), the flap folded over swings back around
    // the fold edge (back grey, front card colour, inner corner r = 5) while the card straightens up with an
    // overshoot, then a double-stripe glint; it sinks away and the next one comes. The first is the logo card (top
    // right, -7°), the others pick corner, fold and tilt at random (same hash as the shader). Card space: 100 units
    // (card x 25..75, y 15..85).
    const float X0 = 25, X1 = 75, Y0 = 15, Y1 = 85, R = 5;
    const double NEXT = 1.6, GAP = 0.3;
    static readonly Color CARDC = Color.FromArgb(124, 124, 131), TAB = Color.FromArgb(95, 95, 99);   // #5f5f63 (Oliver)

    static double Clamp01(double x) { return Math.Max(0, Math.Min(1, x)); }
    static double InOutSine(double x) { return -(Math.Cos(Math.PI * x) - 1) / 2; }
    static double OutBack(double x, double s) { return 1 + (s + 1) * Math.Pow(x - 1, 3) + s * Math.Pow(x - 1, 2); }
    static Color A(Color c, double a) { return Color.FromArgb((int)Math.Round(255 * Clamp01(a) * c.A / 255.0), c.R, c.G, c.B); }

    static void Quad(GraphicsPath p, PointF a, PointF c, PointF b)   // quadratic curve as a cubic one
    {
        p.AddBezier(a, new PointF(a.X + 2f / 3 * (c.X - a.X), a.Y + 2f / 3 * (c.Y - a.Y)),
                    new PointF(b.X + 2f / 3 * (c.X - b.X), b.Y + 2f / 3 * (c.Y - b.Y)), b);
    }

    static double Hash(double n) { double x = Math.Sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.Floor(x); }

    static GraphicsPath CardPath(float f)   // card outline, its top-right corner cut by the fold edge (f = 0: whole)
    {
        var p = new GraphicsPath();
        if (f > 0.01f)
        {
            p.AddLine(X0 + R, Y0, X1 - f, Y0);
            p.AddLine(X1 - f, Y0, X1, Y0 + f);
            p.AddLine(X1, Y0 + f, X1, Y1 - R);
        }
        else
        {
            p.AddLine(X0 + R, Y0, X1 - R, Y0);
            Quad(p, new PointF(X1 - R, Y0), new PointF(X1, Y0), new PointF(X1, Y0 + R));
            p.AddLine(X1, Y0 + R, X1, Y1 - R);
        }
        Quad(p, new PointF(X1, Y1 - R), new PointF(X1, Y1), new PointF(X1 - R, Y1));
        p.AddLine(X1 - R, Y1, X0 + R, Y1);
        Quad(p, new PointF(X0 + R, Y1), new PointF(X0, Y1), new PointF(X0, Y1 - R));
        p.AddLine(X0, Y1 - R, X0, Y0 + R);
        Quad(p, new PointF(X0, Y0 + R), new PointF(X0, Y0), new PointF(X0 + R, Y0));
        p.CloseFigure();
        return p;
    }

    static PointF Toward(PointF p, PointF q, float d)
    {
        float dx = q.X - p.X, dy = q.Y - p.Y, l = (float)Math.Sqrt(dx * dx + dy * dy);
        if (l < 1e-4f) l = 1;
        return new PointF(p.X + dx / l * d, p.Y + dy / l * d);
    }

    // time: seconds since the splash appeared; (cx, cy): centre; unit: pixels per card unit
    public static void DrawLoadCard(Graphics g, double time, float cx, float cy, float unit)
    {
        double T = Math.Max(0, time), n = Math.Floor(T / (NEXT + GAP)), t = T - n * (NEXT + GAP);
        // the first card: the logo (brand/loadcard.json via BrandInfo, tools/build_launcher.py) – without brand/ random
        int corner = BrandInfo.Corner; float F = BrandInfo.Fold; double rot = BrandInfo.Tilt;
        if (n > 0.5 || !BrandInfo.LogoCard)
        {
            corner = (int)Math.Floor(Hash(n) * 4);
            F = (float)(15 + (35 - 15) * Hash(n + 17));
            rot = (Hash(n + 41) < 0.5 ? -1 : 1) * (5 + (20 - 5) * Hash(n + 73));
        }
        double enter = 1 - Math.Pow(1 - Clamp01(t / 0.3), 3);
        double u = Clamp01((t - 0.25) / 0.55), unf = InOutSine(u), str = OutBack(u, 2.2);
        double shim = Clamp01((t - 0.9) / 0.75);
        double alpha = enter, sc = 1.28 - 0.28 * enter;
        if (t > NEXT)
        {   // fades and sinks back, then the next one
            double l = InOutSine(Clamp01((t - NEXT) / GAP));
            alpha *= 1 - l; sc *= 1 - 0.22 * l;
        }
        if (alpha <= 0.001) return;
        var st = g.Save();
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TranslateTransform(cx, cy);
        g.ScaleTransform((float)(unit * sc), (float)(unit * sc));
        g.RotateTransform((float)(rot * (1 - str)));
        var turned = g.Save();
        // drawn with the fold at the top right, mirrored onto its corner (0 top left, 1 top right, 2 bottom right,
        // 3 bottom left – as in the shader)
        g.ScaleTransform(corner == 0 || corner == 3 ? -1 : 1, corner == 2 || corner == 3 ? -1 : 1);
        g.TranslateTransform(-50, -50);
        bool flat = unf >= 0.999;
        using (var body = CardPath(flat ? 0 : F))
        {
            using (var b = new SolidBrush(A(CARDC, alpha))) g.FillPath(b, body);
            using (var shade = new LinearGradientBrush(new PointF(X0, Y0), new PointF(X1, Y1),
                                                      Color.FromArgb(0, 0, 0, 0), A(Color.Black, 0.18 * alpha)))
                g.FillPath(shade, body);
        }
        if (!flat)
        {   // the flap swings around the hinge A-B: tip from the folded-over position to the real corner
            PointF a = new PointF(X1 - F, Y0), b = new PointF(X1, Y0 + F), inner = new PointF(X1 - F, Y0 + F);
            PointF mid = new PointF((a.X + b.X) / 2, (a.Y + b.Y) / 2);
            float k = (float)Math.Cos(Math.PI * unf);
            PointF tip = new PointF(mid.X + (inner.X - mid.X) * k, mid.Y + (inner.Y - mid.Y) * k);
            bool back = k > 0;
            float da = (float)Math.Sqrt((tip.X - a.X) * (tip.X - a.X) + (tip.Y - a.Y) * (tip.Y - a.Y));
            float r = Math.Min(R, 0.45f * da);
            using (var flap = new GraphicsPath())
            {
                PointF ta = Toward(tip, a, r), tb = Toward(tip, b, r);
                flap.AddLine(a, b);
                flap.AddLine(b, tb);
                Quad(flap, tb, tip, ta);
                flap.CloseFigure();
                using (var fb = new SolidBrush(A(back ? TAB : CARDC, alpha))) g.FillPath(fb, flap);
                double up = 1 - Math.Abs(k);
                using (var lb = new SolidBrush(back ? A(Color.Black, 0.25 * up * alpha) : A(Color.White, 0.5 * up * alpha)))
                    g.FillPath(lb, flap);
            }
            if (!back)
            {   // close the hairline seam along the hinge
                using (var whole = CardPath(0))
                using (var pen = new Pen(A(CARDC, alpha), 0.6f))
                {
                    var clip = g.Clip;
                    g.SetClip(whole, CombineMode.Intersect);
                    g.DrawLine(pen, a, b);
                    g.Clip = clip;
                }
            }
        }
        g.Restore(turned);   // the glint is not mirrored: always top left -> bottom right on the screen
        g.TranslateTransform(-50, -50);
        if (shim > 0 && shim < 1)
        {   // double-stripe glint, top left -> bottom right
            double s = -0.25 + 1.5 * InOutSine(shim), am = Math.Sin(Math.PI * shim), light = 1.15, w = 1.4;
            double[] off = { s - 0.12 * w, s - 0.075 * w, s - 0.03 * w, s + 0.005 * w, s + 0.03 * w, s + 0.055 * w };
            double[] val = { 0, light * am, 0, 0, light * 0.9 * am, 0 };
            var pos = new List<float>(); var col = new List<Color>();
            for (int i = 0; i < 6; i++)
            {
                if (off[i] <= 0 || off[i] >= 1) continue;
                if (pos.Count == 0) { pos.Add(0); col.Add(A(Color.White, Math.Min(1, val[i]) * alpha)); }
                pos.Add((float)off[i]); col.Add(A(Color.White, Math.Min(1, val[i]) * alpha));
            }
            if (pos.Count > 0)
            {
                pos.Add(1); col.Add(col[col.Count - 1]);
                using (var whole = CardPath(0))
                using (var gb = new LinearGradientBrush(new PointF(X0 - 10, Y0 - 14), new PointF(X1 + 10, Y1 + 14),
                                                        Color.Transparent, Color.Transparent))
                {
                    gb.InterpolationColors = new ColorBlend { Positions = pos.ToArray(), Colors = col.ToArray() };
                    g.FillPath(gb, whole);
                }
            }
        }
        g.Restore(st);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
        using (var pen = new Pen(Color.FromArgb(34, 34, 34))) g.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);

        if (shownAt < 0) shownAt = clock.ElapsedMilliseconds / 1000.0;
        // the loading card (as in the app): the logo card first, then random ones as long as the splash is there –
        // card 89 px high
        DrawLoadCard(g, clock.ElapsedMilliseconds / 1000.0 - shownAt, Width / 2f, 96.5f, 89f / 70f);

        var center = new StringFormat { Alignment = StringAlignment.Center };
        if (lockup != null)   // the brand: long version (card + BENT°CORNER), drawn at build time (build_launcher.py)
        {
            float lw = lockup.Width / 2f, lh = lockup.Height / 2f;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.DrawImage(lockup, new RectangleF((Width - lw) / 2f, 190 + (34 - lh) / 2f, lw, lh));
        }
        else
            using (var title = new Font("Segoe UI", 16f, FontStyle.Bold))
            using (var ink = new SolidBrush(INK))
                g.DrawString(BrandInfo.Name, title, ink, new RectangleF(0, 190, Width, 34), center);
        using (var small = new Font("Segoe UI", 9.75f))
        using (var muted = new SolidBrush(MUTED))
        using (var ink = new SolidBrush(Color.FromArgb(200, 200, 200)))
        {
            string s = status;
            if (progress >= 0) s += "  " + (int)Math.Round(progress * 100) + " %";
            g.DrawString(s, small, failed ? ink : muted, new RectangleF(20, 228, Width - 40, failed ? 60 : 22), center);
            g.DrawString(sub, small, muted, new RectangleF(20, failed ? 290 : 252, Width - 40, 22), center);
        }
        // dünner Fortschritt (nur beim Auspacken)
        if (progress >= 0)
        {
            float bx = 110, by = Height - 30, bw = Width - 220;
            using (var track = new SolidBrush(Color.FromArgb(34, 34, 34))) g.FillRectangle(track, bx, by, bw, 2);
            using (var bar = new SolidBrush(INK)) g.FillRectangle(bar, bx, by, (float)(bw * Math.Min(1, progress)), 2);
        }
    }
}
