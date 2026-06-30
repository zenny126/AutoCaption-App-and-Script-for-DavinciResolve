-- ============================================================
-- AutoCaption VEC - Generate Captions (OpenAI Whisper API)
-- Chạy script này trong DaVinci Resolve qua: Workspace > Scripts
--
-- Yêu cầu:
--  1. Đã cài Python và thư viện openai (pip install openai)
--  2. Đã set biến môi trường OPENAI_API_KEY
--  3. File transcribe.py đặt cùng thư mục với script này
--     (hoặc sửa PYTHON_SCRIPT_PATH bên dưới cho đúng đường dẫn)
-- ============================================================

resolve = Resolve()
local isWindows = FuPLATFORM_WINDOWS

-- ------------------------------------------------------------
-- CẤU HÌNH: sửa đường dẫn này nếu transcribe.py không cùng thư mục
-- ------------------------------------------------------------
local SCRIPT_DIR = debug.getinfo(1, "S").source:match("@?(.*[\\/])") or "./"
local PYTHON_SCRIPT_PATH = SCRIPT_DIR .. "transcribe_local.py"
local PYTHON_EXE = "python" -- đổi thành "python3" nếu cần trên macOS
local MODEL_SIZE = "medium" -- tiny / base / small / medium / large-v3 (đổi nếu muốn nhanh hơn/chính xác hơn)

-- ------------------------------------------------------------
-- Popup thông báo / hỏi xác nhận (Windows: PowerShell MessageBox)
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- Hộp thoại chọn file (Windows: PowerShell OpenFileDialog)
-- ------------------------------------------------------------
local function pickFile()
    if isWindows then
        local tmpPs1 = os.getenv("TEMP") .. "\\autocaption_vec_pickfile.ps1"
        local tmpOut = os.getenv("TEMP") .. "\\autocaption_vec_pickfile_result.txt"

        local f = io.open(tmpPs1, "w")
        f:write("Add-Type -AssemblyName System.Windows.Forms\n")
        f:write("$dlg = New-Object System.Windows.Forms.OpenFileDialog\n")
        f:write([[$dlg.Filter = "Media Files|*.mp4;*.mov;*.mkv;*.wav;*.mp3;*.m4a;*.avi|All Files|*.*"]] .. "\n")
        f:write("$dlg.Title = 'Chon file audio/video de tao phu de'\n")
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
        local osaCmd = "osascript -e 'POSIX path of (choose file with prompt \"Chon file audio/video\")'"
        local f = io.popen(osaCmd)
        local result = f and f:read("*l") or ""
        if f then f:close() end
        if result == "" then return nil end
        return result
    end
end

-- ------------------------------------------------------------
-- Hộp thoại chọn ngôn ngữ (Windows: PowerShell WinForm tùy chỉnh)
-- ------------------------------------------------------------
local function pickLanguage()
    if isWindows then
        local tmpPs1 = os.getenv("TEMP") .. "\\autocaption_vec_picklang.ps1"
        local tmpOut = os.getenv("TEMP") .. "\\autocaption_vec_picklang_result.txt"

        local f = io.open(tmpPs1, "w")
        f:write([[
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "AutoCaption VEC"
$form.Size = New-Object System.Drawing.Size(360,180)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.Topmost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = "Chon ngon ngu cua audio/video:"
$label.AutoSize = $true
$label.Location = New-Object System.Drawing.Point(20,20)
$form.Controls.Add($label)

$result = ""

function MakeButton($text, $x, $value) {
    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = $text
    $btn.Size = New-Object System.Drawing.Size(75,35)
    $btn.Location = New-Object System.Drawing.Point($x,60)
    $btn.Add_Click({
        $script:result = $value
        $form.Close()
    }.GetNewClosure())
    $form.Controls.Add($btn)
}
]])
        f:write('MakeButton "Tieng Viet" 20 "vi"\n')
        f:write('MakeButton "English" 105 "en"\n')
        f:write('MakeButton "Zhongwen" 190 "zh"\n')
        f:write('MakeButton "Tu nhan dien" 20 "auto"\n')
        -- nút Tự nhận diện đặt xuống dòng dưới
        f:write([[
$btnAuto = $form.Controls | Where-Object { $_.Text -eq "Tu nhan dien" }
$btnAuto.Location = New-Object System.Drawing.Point(20,105)
$btnAuto.Size = New-Object System.Drawing.Size(110,35)

$form.ShowDialog() | Out-Null
Set-Content -Path "]] .. tmpOut .. [[" -Value $result
]])
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

        if result == "" or result == "auto" then return nil end
        return result
    else
        -- macOS: dùng osascript với danh sách lựa chọn
        local osaCmd = [[osascript -e 'choose from list {"Tieng Viet", "English", "Zhongwen", "Tu nhan dien"} with prompt "Chon ngon ngu:"']]
        local f = io.popen(osaCmd)
        local result = f and f:read("*l") or ""
        if f then f:close() end
        if result:find("Tieng Viet") then return "vi"
        elseif result:find("English") then return "en"
        elseif result:find("Zhongwen") then return "zh"
        else return nil end
    end
end

-- ------------------------------------------------------------
-- Gọi Python để transcribe
-- ------------------------------------------------------------
local function runTranscribe(inputPath, outputSrtPath, language)
    local envPrefix = isWindows and "set PYTHONIOENCODING=utf-8 && " or "PYTHONIOENCODING=utf-8 "
    local cmd = string.format(
        '%s%s "%s" "%s" "%s" "%s" "%s"',
        envPrefix, PYTHON_EXE, PYTHON_SCRIPT_PATH, inputPath, outputSrtPath, language or "", MODEL_SIZE
    )
    print("Running: " .. cmd)
    print("Đang xử lý bằng Whisper local (CPU) - có thể mất vài phút tùy độ dài file và model, vui lòng chờ...")

    -- Dùng io.popen để lấy được toàn bộ output (log) của Python, kể cả lỗi.
    local handle = io.popen(cmd .. " 2>&1")
    local output = handle:read("*a")
    local ok, exitType, exitCode = handle:close()
    print("---- Python output ----")
    print(output)
    print("------------------------")

    local success = output:find("OK: Đã tạo file phụ đề") ~= nil
    return success, output
end

-- ------------------------------------------------------------
-- Import file SRT vào timeline hiện tại
-- ------------------------------------------------------------
local function importSrtToTimeline(srtPath)
    local projectManager = resolve:GetProjectManager()
    local project = projectManager:GetCurrentProject()
    if not project then
        return false, "Không tìm thấy project đang mở."
    end

    local timeline = project:GetCurrentTimeline()
    if not timeline then
        return false, "Không tìm thấy timeline đang mở. Hãy mở một timeline trước khi chạy."
    end

    local mediaPool = project:GetMediaPool()

    -- Import file srt vào Media Pool như một media clip.
    local importedItems = mediaPool:ImportMedia({ srtPath })
    if not importedItems or #importedItems == 0 then
        return false, "Import file SRT vào Media Pool thất bại."
    end

    -- Thêm clip phụ đề vào timeline hiện tại.
    local appended = mediaPool:AppendToTimeline(importedItems)
    if not appended or #appended == 0 then
        return false, "Đã import vào Media Pool nhưng không thêm được vào timeline. Bạn có thể tự kéo file SRT từ Media Pool vào timeline theo cách thủ công."
    end

    return true, "Đã thêm phụ đề vào timeline."
end

-- ------------------------------------------------------------
-- MAIN
-- ------------------------------------------------------------
local function Main()
    print("=== AutoCaption VEC - Generate Captions ===")

    local inputFile = pickFile()
    if not inputFile then
        print("Người dùng đã hủy chọn file.")
        return
    end
    print("File đã chọn: " .. inputFile)

    local selectedLang = pickLanguage()
    print("Ngôn ngữ đã chọn: " .. tostring(selectedLang or "tự nhận diện"))

    local srtOutput = (os.getenv("TEMP") or "/tmp") .. "/autocaption_vec_output.srt"
    if not isWindows then
        srtOutput = "/tmp/autocaption_vec_output.srt"
    end

    local success, log = runTranscribe(inputFile, srtOutput, selectedLang)
    if not success then
        showMessage("AutoCaption VEC", "Tạo phụ đề thất bại.\n\nChi tiết log đã in trong Console.", false)
        return
    end

    local importOk, importMsg = importSrtToTimeline(srtOutput)
    if importOk then
        showMessage("AutoCaption VEC", "Đã tạo phụ đề và thêm vào timeline thành công!", false)
    else
        showMessage("AutoCaption VEC",
            "Đã tạo file phụ đề tại:\n" .. srtOutput ..
            "\n\nNhưng tự động thêm vào timeline thất bại: " .. importMsg, false)
    end
end

local ok, err = pcall(Main)
if not ok then
    print("Lỗi: " .. tostring(err))
end
