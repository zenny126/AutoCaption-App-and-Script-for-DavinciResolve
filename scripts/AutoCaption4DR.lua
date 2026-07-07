-- ============================================================
-- AutoCaption - Generate Captions (Local Whisper)
-- Run this script in DaVinci Resolve via: Workspace > Scripts
--
-- Requirements:
--  1. Python 3.9+ installed
--  2. pip install faster-whisper
-- ============================================================

resolve = Resolve()
local isWindows = FuPLATFORM_WINDOWS
local PYTHON_EXE = isWindows and "python" or "python3"
local MODEL = "large-v3-turbo"

-- ============================================================
-- Helpers
-- ============================================================
local function fileExists(p)
    if not p then return false end
    local f = io.open(p, "r")
    if f then f:close(); return true end
    return false
end

local function runPs1(script)
    if not isWindows then return "" end
    local tmpPs1 = os.getenv("TEMP") .. "\\autocaption_tmp.ps1"
    local tmpOut = os.getenv("TEMP") .. "\\autocaption_tmp_result.txt"
    local f = io.open(tmpPs1, "w")
    f:write(script:gsub("__OUT__", tmpOut))
    f:close()
    os.execute('powershell -NoProfile -ExecutionPolicy Bypass -File "' .. tmpPs1 .. '"')
    local result = ""
    local rf = io.open(tmpOut, "r")
    if rf then result = rf:read("*l") or ""; rf:close(); os.remove(tmpOut) end
    os.remove(tmpPs1)
    return result
end

local function showMessage(title, message, askYesNo)
    if isWindows then
        local buttons = askYesNo and "YesNo" or "OK"
        local icon = askYesNo and "Question" or "Information"
        local result = runPs1(
            "Add-Type -AssemblyName System.Windows.Forms\n" ..
            "$r = [System.Windows.Forms.MessageBox]::Show(@'\n" .. message .. "\n'@, @'\n" .. title .. "\n'@, " ..
            "[System.Windows.Forms.MessageBoxButtons]::" .. buttons .. ", " ..
            "[System.Windows.Forms.MessageBoxIcon]::" .. icon .. ")\n" ..
            "Set-Content -Path '__OUT__' -Value $r\n"
        )
        return result:gsub("%s+", "") == "Yes"
    else
        local safeMsg = message:gsub('"', '\\"'):gsub("\n", " ")
        local safeTitle = title:gsub('"', '\\"')
        local buttons = askYesNo and '{"No", "Yes"}' or '{"OK"}'
        local f = io.popen(string.format(
            'osascript -e \'display dialog "%s" with title "%s" buttons %s default button "%s"\'',
            safeMsg, safeTitle, buttons, askYesNo and "Yes" or "OK"
        ))
        local result = f and f:read("*a") or ""
        if f then f:close() end
        return result:find("Yes") ~= nil
    end
end

local function pickFile()
    if isWindows then
        local result = runPs1(
            'Add-Type -AssemblyName System.Windows.Forms\n' ..
            '$dlg = New-Object System.Windows.Forms.OpenFileDialog\n' ..
            '$dlg.Filter = "Media Files|*.mp4;*.mov;*.mkv;*.wav;*.mp3;*.m4a;*.avi|All Files|*.*"\n' ..
            "$dlg.Title = 'Select audio/video file'\n" ..
            "if ($dlg.ShowDialog() -eq 'OK') { Set-Content -Path '__OUT__' -Value $dlg.FileName }" ..
            " else { Set-Content -Path '__OUT__' -Value '' }\n"
        )
        return result ~= "" and result or nil
    else
        local f = io.popen("osascript -e 'POSIX path of (choose file with prompt \"Select audio/video file\")'")
        local result = f and f:read("*l") or ""
        if f then f:close() end
        return result ~= "" and result or nil
    end
end

-- ============================================================
-- Transcribe (embedded Python)
-- ============================================================
local function runTranscribe(inputPath, outputSrtPath)
    local pyCode = [[
import sys, os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except: pass

def fmt(s):
    if s < 0: s = 0
    return f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{int(s%60):02d},{int(round((s-int(s))*1000)):03d}"

try:
    from faster_whisper import WhisperModel
    import ctranslate2
    has_cuda = ctranslate2.get_cuda_device_count() > 0
except: has_cuda = False

device = "cuda" if has_cuda else "cpu"
m_size = sys.argv[3] if len(sys.argv)>3 and sys.argv[3] else "large-v3-turbo"

print(f"Loading model '{m_size}' on {device.upper()}...")
try:
    m = WhisperModel(m_size, device=device, compute_type="float16" if device=="cuda" else "int8")
    print(f"Processing audio: {sys.argv[1]}")
    segs, info = m.transcribe(sys.argv[1], beam_size=5, vad_filter=True)
    print(f"Detected language: {info.language}")
    duration = info.duration
    srt, idx = "", 1
    for s in segs:
        sc = min(s.start, duration) if duration else s.start
        ec = min(s.end, duration) if duration else s.end
        if duration and sc >= duration: continue
        srt += f"{idx}\n{fmt(sc)} --> {fmt(ec)}\n{s.text.strip()}\n\n"
        idx += 1
    with open(sys.argv[2], "w", encoding="utf-8") as f: f.write(srt)
    print(f"OK: Subtitle file created at {sys.argv[2]}")
except Exception as e:
    print(f"ERROR: {e}")
]]
    local tmpPy = isWindows and (os.getenv("TEMP") .. "\\autocaption_runner.py") or "/tmp/autocaption_runner.py"
    local f = io.open(tmpPy, "w")
    if f then f:write(pyCode); f:close() end

    local envPrefix = isWindows and "set PYTHONIOENCODING=utf-8 && " or "PYTHONIOENCODING=utf-8 "
    local cmd = string.format('%s%s "%s" "%s" "%s" "%s"',
        envPrefix, PYTHON_EXE, tmpPy, inputPath, outputSrtPath, MODEL)
    print("Running: " .. cmd)
    print("Processing with local Whisper - please wait...")

    local handle = io.popen(cmd .. " 2>&1")
    local output = handle:read("*a")
    handle:close()
    os.remove(tmpPy)

    print("---- Python output ----")
    print(output)
    print("------------------------")
    return output:find("OK:") ~= nil, output
end

-- ============================================================
-- Import SRT into Media Pool + Timeline
-- ============================================================
local function importToMediaPool(srtPath)
    local projectManager = resolve:GetProjectManager()
    local project = projectManager and projectManager:GetCurrentProject()
    if not project then return false end

    local mediaPool = project:GetMediaPool()
    if not mediaPool then return false end

    local imported = mediaPool:ImportMedia({srtPath})
    if not imported or #imported == 0 then return false end

    local timeline = project:GetCurrentTimeline()
    if timeline then mediaPool:AppendToTimeline(imported) end
    return true
end

-- ============================================================
-- MAIN
-- ============================================================
local function Main()
    print("=== AutoCaption - Generate Captions ===")

    -- 1. Select input file
    local inputFile = pickFile()
    if not inputFile then print("Cancelled."); return end
    print("Selected file: " .. inputFile)

    -- 2. Transcribe (output SRT next to input file)
    local srtPath = inputFile:gsub("%.%w+$", "") .. ".srt"

    local success = runTranscribe(inputFile, srtPath)
    if not success then
        showMessage("AutoCaption", "Subtitle generation failed.\n\nSee Console for details.", false)
        return
    end

    if not fileExists(srtPath) then
        showMessage("AutoCaption", "SRT file not found after processing.\nCheck Console for details.", false)
        return
    end

    -- 3. Import to Media Pool
    if importToMediaPool(srtPath) then
        showMessage("AutoCaption", "SRT imported into Media Pool successfully!\n\nFile: " .. srtPath, false)
    else
        showMessage("AutoCaption", "SRT file created at:\n" .. srtPath ..
            "\n\nAutomatic import failed. Please drag it into Media Pool manually.", false)
    end
end

local ok, err = pcall(Main)
if not ok then print("Error: " .. tostring(err)) end