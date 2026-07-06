-- ============================================================
-- AutoCaption VEC - Generate Captions (Local Whisper)
-- Run this script in DaVinci Resolve via: Workspace > Scripts
--
-- Requirements:
--  1. Python 3.9+ installed
--  2. Dependencies: pip install -r requirements.txt
--  3. transcribe_local.py in same folder as this script
-- ============================================================

resolve = Resolve()
local isWindows = FuPLATFORM_WINDOWS

-- ============================================================
-- CONFIGURATION
-- ============================================================
local SCRIPT_DIR = debug.getinfo(1, "S").source:match("@?(.*[\\/])")
local PYTHON_SCRIPT_PATH = SCRIPT_DIR .. "transcribe_local.py"
local PYTHON_EXE = "python" -- change to "python3" on macOS if needed

-- ============================================================
-- Message box (Windows: PowerShell MessageBox)
-- ============================================================
local function showMessage(title, message, askYesNo)
    if isWindows then
        local buttons = askYesNo and "YesNo" or "OK"
        local icon = askYesNo and "Question" or "Information"
        local tmpPs1 = os.getenv("TEMP") .. "\\autocaption_vec_msgbox.ps1"
        local tmpOut = os.getenv("TEMP") .. "\\autocaption_vec_msgbox_result.txt"

        local f = io.open(tmpPs1, "w")
        f:write("Add-Type -AssemblyName System.Windows.Forms\n")
        f:write("$title = @'\n" .. title .. "\n'@\n")
        f:write("$message = @'\n" .. message .. "\n'@\n")
        f:write("$r = [System.Windows.Forms.MessageBox]::Show($message, $title, " ..
                "[System.Windows.Forms.MessageBoxButtons]::" .. buttons .. ", " ..
                "[System.Windows.Forms.MessageBoxIcon]::" .. icon .. ")\n")
        f:write("Set-Content -Path '" .. tmpOut .. "' -Value $r\n")
        f:close()

        os.execute('powershell -NoProfile -ExecutionPolicy Bypass -File "' .. tmpPs1 .. '"')

        local result = ""
        local rf = io.open(tmpOut, "r")
        if rf then
            result = rf:read("*l") or ""
            rf:close()
            os.remove(tmpOut)
        end
        os.remove(tmpPs1)
        return result:gsub("%s+", "") == "Yes"
    else
        local safeTitle = title:gsub('"', '\\"')
        local safeMessage = message:gsub('"', '\\"'):gsub("\n", " ")
        local buttons = askYesNo and '{"No", "Yes"}' or '{"OK"}'
        local osaCmd = string.format(
            'osascript -e \'display dialog "%s" with title "%s" buttons %s default button "%s"\'',
            safeMessage, safeTitle, buttons, askYesNo and "Yes" or "OK"
        )
        local f = io.popen(osaCmd)
        local result = f and f:read("*a") or ""
        if f then f:close() end
        return result:find("Yes") ~= nil
    end
end

-- ============================================================
-- File picker - chọn file đầu vào
-- ============================================================
local function pickFile()
    if isWindows then
        local tmpPs1 = os.getenv("TEMP") .. "\\autocaption_vec_pickfile.ps1"
        local tmpOut = os.getenv("TEMP") .. "\\autocaption_vec_pickfile_result.txt"

        local f = io.open(tmpPs1, "w")
        f:write("Add-Type -AssemblyName System.Windows.Forms\n")
        f:write("$dlg = New-Object System.Windows.Forms.OpenFileDialog\n")
        f:write([[$dlg.Filter = "Media Files|*.mp4;*.mov;*.mkv;*.wav;*.mp3;*.m4a;*.avi|All Files|*.*"]] .. "\n")
        f:write("$dlg.Title = 'Select audio/video file to create subtitles'\n")
        f:write("if ($dlg.ShowDialog() -eq 'OK') {\n")
        f:write("  Set-Content -Path '" .. tmpOut .. "' -Value $dlg.FileName\n")
        f:write("} else {\n")
        f:write("  Set-Content -Path '" .. tmpOut .. "' -Value ''\n")
        f:write("}\n")
        f:close()

        os.execute('powershell -NoProfile -ExecutionPolicy Bypass -File "' .. tmpPs1 .. '"')

        local result = ""
        local rf = io.open(tmpOut, "r")
        if rf then
            result = rf:read("*l") or ""
            rf:close()
            os.remove(tmpOut)
        end
        os.remove(tmpPs1)
        if result == "" then return nil end
        return result
    else
        local osaCmd = "osascript -e 'POSIX path of (choose file with prompt \"Select audio/video file\")'"
        local f = io.popen(osaCmd)
        local result = f and f:read("*l") or ""
        if f then f:close() end
        if result == "" then return nil end
        return result
    end
end

-- ============================================================
-- Folder picker - chọn thư mục lưu file SRT thủ công
-- ============================================================
local function pickSaveFolder(defaultPath)
    if isWindows then
        local tmpPs1 = os.getenv("TEMP") .. "\\autocaption_vec_pickfolder.ps1"
        local tmpOut = os.getenv("TEMP") .. "\\autocaption_vec_pickfolder_result.txt"

        local f = io.open(tmpPs1, "w")
        f:write("Add-Type -AssemblyName System.Windows.Forms\n")
        f:write("$dlg = New-Object System.Windows.Forms.FolderBrowserDialog\n")
        f:write("$dlg.Description = 'Select folder to save SRT subtitle file(s)'\n")
        f:write("$dlg.SelectedPath = '" .. (defaultPath or os.getenv("USERPROFILE") or "C:\\") .. "'\n")
        f:write("if ($dlg.ShowDialog() -eq 'OK') {\n")
        f:write("  Set-Content -Path '" .. tmpOut .. "' -Value $dlg.SelectedPath\n")
        f:write("} else {\n")
        f:write("  Set-Content -Path '" .. tmpOut .. "' -Value ''\n")
        f:write("}\n")
        f:close()

        os.execute('powershell -NoProfile -ExecutionPolicy Bypass -File "' .. tmpPs1 .. '"')

        local result = ""
        local rf = io.open(tmpOut, "r")
        if rf then
            result = rf:read("*l") or ""
            rf:close()
            os.remove(tmpOut)
        end
        os.remove(tmpPs1)
        if result == "" then return nil end
        return result
    else
        local osaCmd = "osascript -e 'POSIX path of (choose folder with prompt \"Select folder to save SRT file(s)\")'"
        local f = io.popen(osaCmd)
        local result = f and f:read("*l") or ""
        if f then f:close() end
        if result == "" then return nil end
        return result
    end
end

-- ============================================================
-- Dialog chọn ngôn ngữ, model, số file xuất
-- ============================================================
local function pickSettings()
    if isWindows then
        local tmpPs1 = os.getenv("TEMP") .. "\\autocaption_vec_picklang.ps1"
        local tmpOut = os.getenv("TEMP") .. "\\autocaption_vec_picklang_result.txt"

        local f = io.open(tmpPs1, "w")
        f:write([[
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "AutoCaption VEC - Settings"
$form.Size = New-Object System.Drawing.Size(500,350)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.Topmost = $true

$langLabel = New-Object System.Windows.Forms.Label
$langLabel.Text = "Source Language:"
$langLabel.Location = New-Object System.Drawing.Point(20,20)
$langLabel.Size = New-Object System.Drawing.Size(150,20)
$form.Controls.Add($langLabel)

$langDropdown = New-Object System.Windows.Forms.ComboBox
$langDropdown.Items.AddRange(@("Vietnamese", "English", "Chinese", "Auto-detect"))
$langDropdown.SelectedIndex = 3
$langDropdown.Location = New-Object System.Drawing.Point(180,20)
$langDropdown.Size = New-Object System.Drawing.Size(280,25)
$langDropdown.DropDownStyle = "DropDownList"
$form.Controls.Add($langDropdown)

$modelLabel = New-Object System.Windows.Forms.Label
$modelLabel.Text = "Model:"
$modelLabel.Location = New-Object System.Drawing.Point(20,60)
$modelLabel.Size = New-Object System.Drawing.Size(150,20)
$form.Controls.Add($modelLabel)

$modelDropdown = New-Object System.Windows.Forms.ComboBox
$modelDropdown.Items.AddRange(@("tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"))
$modelDropdown.SelectedIndex = 3
$modelDropdown.Location = New-Object System.Drawing.Point(180,60)
$modelDropdown.Size = New-Object System.Drawing.Size(280,25)
$modelDropdown.DropDownStyle = "DropDownList"
$form.Controls.Add($modelDropdown)

$outputLabel = New-Object System.Windows.Forms.Label
$outputLabel.Text = "Output Files:"
$outputLabel.Location = New-Object System.Drawing.Point(20,100)
$outputLabel.Size = New-Object System.Drawing.Size(150,20)
$form.Controls.Add($outputLabel)

$outputDropdown = New-Object System.Windows.Forms.ComboBox
$outputDropdown.Items.AddRange(@("1 File (Original only)", "2 Files (Original + Translation)"))
$outputDropdown.SelectedIndex = 0
$outputDropdown.Location = New-Object System.Drawing.Point(180,100)
$outputDropdown.Size = New-Object System.Drawing.Size(280,25)
$outputDropdown.DropDownStyle = "DropDownList"
$form.Controls.Add($outputDropdown)

$transLabel = New-Object System.Windows.Forms.Label
$transLabel.Text = "Translation Language:"
$transLabel.Location = New-Object System.Drawing.Point(20,140)
$transLabel.Size = New-Object System.Drawing.Size(150,20)
$transLabel.Enabled = $false
$form.Controls.Add($transLabel)

$transDropdown = New-Object System.Windows.Forms.ComboBox
$transDropdown.Items.AddRange(@("English", "Vietnamese", "Chinese", "Spanish", "French", "German", "Japanese", "Korean"))
$transDropdown.SelectedIndex = 0
$transDropdown.Location = New-Object System.Drawing.Point(180,140)
$transDropdown.Size = New-Object System.Drawing.Size(280,25)
$transDropdown.DropDownStyle = "DropDownList"
$transDropdown.Enabled = $false
$form.Controls.Add($transDropdown)

$outputDropdown.Add_SelectedIndexChanged({
    $enable = ($outputDropdown.SelectedIndex -eq 1)
    $transLabel.Enabled = $enable
    $transDropdown.Enabled = $enable
})

$okBtn = New-Object System.Windows.Forms.Button
$okBtn.Text = "OK"
$okBtn.Location = New-Object System.Drawing.Point(180,200)
$okBtn.Size = New-Object System.Drawing.Size(90,35)
$okBtn.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.Controls.Add($okBtn)

$cancelBtn = New-Object System.Windows.Forms.Button
$cancelBtn.Text = "Cancel"
$cancelBtn.Location = New-Object System.Drawing.Point(280,200)
$cancelBtn.Size = New-Object System.Drawing.Size(90,35)
$cancelBtn.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($cancelBtn)

$form.AcceptButton = $okBtn
$form.CancelButton = $cancelBtn

$result = $form.ShowDialog()

if ($result -eq "OK") {
    $lang = switch ($langDropdown.SelectedIndex) {
        0 { "vi" } 1 { "en" } 2 { "zh" } default { "auto" }
    }
    $model = $modelDropdown.SelectedItem
    $output = if ($outputDropdown.SelectedIndex -eq 0) { "1" } else { "2" }
    $trans = switch ($transDropdown.SelectedIndex) {
        0 { "en" } 1 { "vi" } 2 { "zh" } 3 { "es" } 4 { "fr" } 5 { "de" } 6 { "ja" } 7 { "ko" } default { "en" }
    }
    Set-Content -Path "]] .. tmpOut .. [[" -Value "$lang|$model|$output|$trans"
} else {
    Set-Content -Path "]] .. tmpOut .. [[" -Value "CANCEL"
}
]])
        f:close()

        os.execute('powershell -NoProfile -ExecutionPolicy Bypass -File "' .. tmpPs1 .. '"')
        os.execute("timeout /t 1 /nobreak >nul 2>&1")

        local result = ""
        local rf = io.open(tmpOut, "r")
        if rf then
            result = rf:read("*l") or "CANCEL"
            rf:close()
            os.remove(tmpOut)
        end
        os.remove(tmpPs1)

        if result == "CANCEL" then return nil end

        local parts = {}
        for part in result:gmatch("[^|]+") do table.insert(parts, part) end
        local lang = parts[1] == "auto" and nil or parts[1]
        print("DEBUG: lang=" .. tostring(lang) .. ", model=" .. tostring(parts[2]) .. ", output=" .. tostring(parts[3]) .. ", trans=" .. tostring(parts[4]))
        return lang, parts[2], parts[3], parts[4]
    else
        return nil, "medium", "1", "en"
    end
end

-- ============================================================
-- Call Python để transcribe
-- ============================================================
local function runTranscribe(inputPath, outputSrtPath, language, model, outputFiles, targetLang)
    local envPrefix = isWindows and "set PYTHONIOENCODING=utf-8 && " or "PYTHONIOENCODING=utf-8 "
    local cmd = string.format(
        '%s%s "%s" "%s" "%s" "%s" "%s" "%s" "%s"',
        envPrefix, PYTHON_EXE, PYTHON_SCRIPT_PATH,
        inputPath, outputSrtPath,
        language or "", model or "medium", targetLang or "", outputFiles or "1"
    )
    print("Running: " .. cmd)
    print("Processing with local Whisper (CPU) - may take a few minutes. Please wait...")

    local handle = io.popen(cmd .. " 2>&1")
    local output = handle:read("*a")
    handle:close()
    print("---- Python output ----")
    print(output)
    print("------------------------")

    return output:find("OK:") ~= nil, output
end

-- ============================================================
-- Import SRT vào Media Pool + Timeline
-- Trả về: ok (bool), msg (string), importedPaths (table)
-- ============================================================
local function importToMediaPool(paths)
    local projectManager = resolve:GetProjectManager()
    local project = projectManager and projectManager:GetCurrentProject()
    if not project then return false, "Không tìm thấy project đang mở.", {} end

    local mediaPool = project:GetMediaPool()
    if not mediaPool then return false, "Không truy cập được Media Pool.", {} end

    local toImport = {}
    for _, p in ipairs(paths) do
        if p then table.insert(toImport, p) end
    end

    local imported = mediaPool:ImportMedia(toImport)
    if not imported or #imported == 0 then
        return false, "ImportMedia() thất bại.", {}
    end

    -- Thử thêm vào timeline (không bắt buộc phải thành công)
    local timeline = project:GetCurrentTimeline()
    if timeline then
        mediaPool:AppendToTimeline(imported)
    end

    return true, "Đã import vào Media Pool (" .. #imported .. " file).", imported
end

-- ============================================================
-- MAIN
-- ============================================================
local function Main()
    print("=== AutoCaption VEC - Generate Captions ===")

    -- 1. Chọn file đầu vào
    local inputFile = pickFile()
    if not inputFile then
        print("Cancelled by user.")
        return
    end
    print("Selected file: " .. inputFile)

    -- 2. Chọn cài đặt
    local selectedLang, model, outputFormat, targetLang = pickSettings()
    if not model then
        print("Cancelled by user.")
        return
    end

    -- 3. Xác định đường dẫn file SRT tạm (trong TEMP, sau đó sẽ import)
    local tempDir = (isWindows and os.getenv("TEMP")) or "/tmp"
    local srtMain = tempDir .. (isWindows and "\\" or "/") .. "autocaption_vec_output.srt"
    local srtTrans = nil
    if outputFormat == "2" and targetLang and targetLang ~= "" then
        srtTrans = tempDir .. (isWindows and "\\" or "/") .. "autocaption_vec_output_" .. targetLang .. ".srt"
    end

    -- 4. Chạy Python transcribe
    local success, log = runTranscribe(inputFile, srtMain, selectedLang, model, outputFormat, targetLang)
    if not success then
        showMessage("AutoCaption VEC", "Tạo phụ đề thất bại.\n\nXem chi tiết lỗi trong Console.", false)
        return
    end

    -- 5. Danh sách file SRT đã tạo thành công
    local srtFiles = {}
    local function fileExists(p)
        if not p then return false end
        local f = io.open(p, "r")
        if f then f:close(); return true end
        return false
    end
    if fileExists(srtMain) then table.insert(srtFiles, srtMain) end
    if fileExists(srtTrans) then table.insert(srtFiles, srtTrans) end

    if #srtFiles == 0 then
        showMessage("AutoCaption VEC", "Không tìm thấy file SRT sau khi xử lý. Xem Console để biết chi tiết.", false)
        return
    end

    -- 6. Import vào Media Pool (mặc định)
    local importOk, importMsg = importToMediaPool(srtFiles)
    if importOk then
        local infoMsg = "Đã import " .. #srtFiles .. " file SRT vào Media Pool thành công!"
        if outputFormat == "2" then
            infoMsg = infoMsg .. "\n\nFile gốc: " .. srtMain
            if srtTrans then infoMsg = infoMsg .. "\nFile dịch: " .. srtTrans end
        end
        showMessage("AutoCaption VEC", infoMsg, false)
        return
    end

    -- 7. Import tự động thất bại → hỏi người dùng có muốn tự chọn vị trí lưu không
    print("Import vào Media Pool thất bại: " .. importMsg)
    local wantManual = showMessage(
        "AutoCaption VEC",
        "Không thể tự động import vào Media Pool.\n\n" ..
        "Bạn có muốn chọn thư mục để lưu file SRT thủ công không?\n" ..
        "(Sau đó bạn có thể tự kéo file vào Media Pool / Timeline)",
        true
    )

    if not wantManual then
        showMessage("AutoCaption VEC",
            "Đã tạo file SRT tại:\n" ..
            table.concat(srtFiles, "\n") ..
            "\n\nHãy kéo thủ công vào Media Pool.", false)
        return
    end

    -- 8. Người dùng chọn thư mục lưu
    local saveFolder = pickSaveFolder(os.getenv("USERPROFILE") or os.getenv("HOME"))
    if not saveFolder then
        showMessage("AutoCaption VEC",
            "Không chọn thư mục. File SRT tạm vẫn nằm tại:\n" .. table.concat(srtFiles, "\n"), false)
        return
    end

    -- 9. Copy file SRT sang thư mục đã chọn
    local sep = isWindows and "\\" or "/"
    local finalPaths = {}
    for _, srcPath in ipairs(srtFiles) do
        local filename = srcPath:match("[/\\]([^/\\]+)$")
        local destPath = saveFolder .. sep .. filename
        local copyCmd = isWindows
            and ('copy /Y "' .. srcPath .. '" "' .. destPath .. '" >nul')
            or  ('cp "' .. srcPath .. '" "' .. destPath .. '"')
        os.execute(copyCmd)
        if fileExists(destPath) then
            table.insert(finalPaths, destPath)
        end
    end

    if #finalPaths == 0 then
        showMessage("AutoCaption VEC", "Copy file thất bại. File SRT tạm vẫn tại:\n" .. table.concat(srtFiles, "\n"), false)
        return
    end

    -- 10. Thử import lại từ vị trí đã chọn
    local importOk2 = importToMediaPool(finalPaths)
    if importOk2 then
        showMessage("AutoCaption VEC",
            "Đã lưu và import " .. #finalPaths .. " file SRT vào Media Pool thành công!\n\n" ..
            table.concat(finalPaths, "\n"), false)
    else
        showMessage("AutoCaption VEC",
            "Đã lưu file SRT tại:\n" ..
            table.concat(finalPaths, "\n") ..
            "\n\nHãy kéo thủ công từ vị trí này vào Media Pool.", false)
    end
end

local ok, err = pcall(Main)
if not ok then
    print("Error: " .. tostring(err))
end