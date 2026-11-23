# Shared Bellalun/VXvue launcher screens (frame/FRAME.md 2.2, REQ-FRAME-001).
# ASCII only: every visible string comes from the Python JSON payload (core/frame_ui.py).
# Screens: home, inspect, confirm, progress, result. Answer JSON is written to -Out.
param([string]$In, [string]$Out, [string]$Snapshot = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$d = [IO.File]::ReadAllText($In, [Text.Encoding]::UTF8) | ConvertFrom-Json
$script:answer = @{action = 'close'}

function Rgb($hex) { [Drawing.ColorTranslator]::FromHtml($hex) }
$palette = @{}
foreach ($p in $d.palette.PSObject.Properties) { $palette[$p.Name] = Rgb $p.Value }
function Tone($level) { if ($palette.ContainsKey([string]$level)) { $palette[[string]$level] } else { $palette['text'] } }

$f = New-Object Windows.Forms.Form
$f.Text = $d.window_title
$f.Size = New-Object Drawing.Size(920, 720)
$f.MinimumSize = New-Object Drawing.Size(760, 560)
$f.StartPosition = 'CenterScreen'
$f.Font = New-Object Drawing.Font('Malgun Gothic', 10)
$f.BackColor = Rgb '#f1f5f9'

# Header: product, step indicator, heading.
$header = New-Object Windows.Forms.Panel
$header.Dock = 'Top'; $header.Height = 118; $header.BackColor = [Drawing.Color]::White; $header.Padding = '24,12,24,8'
$eyebrow = New-Object Windows.Forms.Label
$eyebrow.Text = $d.product; $eyebrow.AutoSize = $true; $eyebrow.ForeColor = Rgb '#527087'
$eyebrow.Font = New-Object Drawing.Font('Malgun Gothic', 9, [Drawing.FontStyle]::Bold); $eyebrow.Location = '24,10'
$header.Controls.Add($eyebrow)
$x = 24
for ($i = 0; $i -lt @($d.steps).Count; $i++) {
    $s = New-Object Windows.Forms.Label
    $s.AutoSize = $true; $s.Location = New-Object Drawing.Point($x, 34)
    $s.Text = ('{0}. {1}' -f ($i + 1), $d.steps[$i])
    if ($i -eq [int]$d.step_index) {
        $s.Font = New-Object Drawing.Font('Malgun Gothic', 10, [Drawing.FontStyle]::Bold); $s.ForeColor = Rgb '#186b96'
    } else { $s.ForeColor = Rgb '#8a99a8' }
    $header.Controls.Add($s)
    $x += [Windows.Forms.TextRenderer]::MeasureText($s.Text, $s.Font).Width + 26
}
$heading = New-Object Windows.Forms.Label
$heading.Text = $d.heading; $heading.AutoSize = $true; $heading.Location = '22,62'
$heading.Font = New-Object Drawing.Font('Malgun Gothic', 17, [Drawing.FontStyle]::Bold); $heading.ForeColor = Rgb '#182638'
$header.Controls.Add($heading)

# Footer buttons.
$footer = New-Object Windows.Forms.FlowLayoutPanel
$footer.Dock = 'Bottom'; $footer.Height = 64; $footer.Padding = '20,12,20,12'; $footer.FlowDirection = 'RightToLeft'
$footer.BackColor = [Drawing.Color]::White

$body = New-Object Windows.Forms.FlowLayoutPanel
$body.Dock = 'Fill'; $body.FlowDirection = 'TopDown'; $body.WrapContents = $false; $body.AutoScroll = $true
$body.Padding = '24,16,24,16'
$f.Controls.Add($body); $f.Controls.Add($footer); $f.Controls.Add($header)
$width = 840

function Add-Text($text, $size = 10, $bold = $false, $color = '#182638') {
    $l = New-Object Windows.Forms.Label
    $l.Text = [string]$text; $l.AutoSize = $true; $l.MaximumSize = New-Object Drawing.Size($width, 0)
    $style = if ($bold) { [Drawing.FontStyle]::Bold } else { [Drawing.FontStyle]::Regular }
    $l.Font = New-Object Drawing.Font('Malgun Gothic', $size, $style); $l.ForeColor = Rgb $color
    $l.Margin = '0,4,0,6'; $body.Controls.Add($l); return $l
}
function Add-Banner($text, $level) {
    $p = New-Object Windows.Forms.Panel
    $p.Width = $width; $p.Height = 58; $p.BackColor = [Drawing.Color]::White; $p.Margin = '0,4,0,12'
    $bar = New-Object Windows.Forms.Panel; $bar.Dock = 'Left'; $bar.Width = 6; $bar.BackColor = Tone $level
    $l = New-Object Windows.Forms.Label; $l.Text = [string]$text; $l.AutoSize = $false; $l.Dock = 'Fill'
    $l.TextAlign = 'MiddleLeft'; $l.Padding = '14,0,0,0'; $l.ForeColor = Tone $level
    $l.Font = New-Object Drawing.Font('Malgun Gothic', 13, [Drawing.FontStyle]::Bold)
    $p.Controls.Add($l); $p.Controls.Add($bar); $body.Controls.Add($p); return $l
}
function Add-Table($columns, $rows, $height = 260) {
    $g = New-Object Windows.Forms.DataGridView
    $g.Width = $width; $g.Height = $height; $g.ReadOnly = $true; $g.AllowUserToAddRows = $false
    $g.AllowUserToDeleteRows = $false; $g.RowHeadersVisible = $false; $g.MultiSelect = $false
    $g.AutoSizeRowsMode = 'AllCells'; $g.BackgroundColor = [Drawing.Color]::White; $g.BorderStyle = 'None'
    $g.DefaultCellStyle.WrapMode = 'True'; $g.ColumnHeadersHeightSizeMode = 'AutoSize'
    $g.EnableHeadersVisualStyles = $false; $g.ColumnHeadersDefaultCellStyle.BackColor = Rgb '#e8edf6'
    # Keep status colours readable: selection must not repaint the row blue.
    $g.DefaultCellStyle.SelectionBackColor = [Drawing.Color]::White; $g.DefaultCellStyle.SelectionForeColor = Rgb '#182638'
    $g.Add_DataBindingComplete({ $this.ClearSelection() }); $f.Add_Shown({ foreach ($c in $body.Controls) { if ($c -is [Windows.Forms.DataGridView]) { $c.ClearSelection(); $c.CurrentCell = $null } } })
    foreach ($c in $columns) {
        [void]$g.Columns.Add($c.key, $c.label); $g.Columns[$c.key].Width = [int]$c.width
        $g.Columns[$c.key].SortMode = 'NotSortable'
    }
    Fill-Table $g $columns $rows
    $body.Controls.Add($g); return $g
}
function Fill-Table($g, $columns, $rows) {
    $g.Rows.Clear()
    foreach ($r in @($rows)) {
        $values = @(); foreach ($c in $columns) { $values += [string]$r.($c.key) }
        $idx = $g.Rows.Add([object[]]$values)
        $g.Rows[$idx].Cells[0].Style.ForeColor = Tone $r.level
        $g.Rows[$idx].Cells[0].Style.SelectionForeColor = Tone $r.level
        $g.Rows[$idx].Cells[0].Style.Font = New-Object Drawing.Font('Malgun Gothic', 10, [Drawing.FontStyle]::Bold)
    }
    $g.ClearSelection()
}
function Paint-Primary($b) {
    if ($b.Enabled) { $b.BackColor = Rgb '#186b96'; $b.ForeColor = [Drawing.Color]::White }
    else { $b.BackColor = Rgb '#d5dde6'; $b.ForeColor = Rgb '#7c8794' }
}
function Add-Button($parent, $choice) {
    $b = New-Object Windows.Forms.Button
    $b.Text = $choice.label; $b.AutoSize = $true; $b.Height = 38; $b.Padding = '10,0,10,0'; $b.Margin = '6,0,0,0'
    $b.Tag = $choice
    if ($choice.primary) {
        $b.FlatStyle = 'Flat'; $b.Font = New-Object Drawing.Font('Malgun Gothic', 10, [Drawing.FontStyle]::Bold)
        $b.Add_EnabledChanged({ Paint-Primary $this }); Paint-Primary $b
    }
    if ($null -ne $choice.enabled) { $b.Enabled = [bool]$choice.enabled }
    if ($choice.primary) { Paint-Primary $b }
    $b.Add_Click({
        $c = $this.Tag
        if ($c.open) { try { Start-Process -FilePath $c.open } catch {} ; return }
        Finish-With $c.key
    })
    $parent.Controls.Add($b); return $b
}
function Selected-Options {
    $o = @{}; foreach ($k in $script:combos.Keys) { $o[$k] = $d.options_by_key.$k.choices[$script:combos[$k].SelectedIndex].key }; return $o
}
function Finish-With($action) {
    $script:answer = @{action = $action; options = (Selected-Options)}
    if ($d.screen -eq 'confirm') {
        $keys = @(); for ($i = 0; $i -lt $checks.Items.Count; $i++) { if ($checks.GetItemChecked($i)) { $keys += $d.checks[$i].key } }
        $values = @{}; foreach ($k in $script:toggles.Keys) { $values[$k] = $script:toggles[$k].Checked }
        $script:answer.checked = $keys; $script:answer.toggles = $values
    }
    $f.Close()
}
$script:combos = @{}

switch ($d.screen) {
    'home' {
        foreach ($line in @($d.lines)) { Add-Text $line 11 }
        if ($d.last_result) {
            Add-Text $d.last_result_label 10 $true '#527087' | Out-Null
            Add-Banner $d.last_result.text $d.last_result.level | Out-Null
        }
        foreach ($tip in @($d.tips)) { Add-Text $tip 9 $false '#66778a' | Out-Null }
    }
    'inspect' {
        $banner = Add-Banner $d.headline.text $d.headline.level
        foreach ($note in @($d.notes)) { Add-Text $note 9 $false '#527087' | Out-Null }
        foreach ($opt in @($d.options)) {
            Add-Text $opt.label 10 $true | Out-Null
            $cb = New-Object Windows.Forms.ComboBox; $cb.DropDownStyle = 'DropDownList'; $cb.Width = 420
            foreach ($c in $opt.choices) { [void]$cb.Items.Add($c.label) }
            $cb.SelectedIndex = 0
            for ($i = 0; $i -lt @($opt.choices).Count; $i++) { if ($opt.choices[$i].key -eq $opt.value) { $cb.SelectedIndex = $i } }
            $body.Controls.Add($cb); $script:combos[$opt.key] = $cb
        }
        $grid = Add-Table $d.columns $d.rows 280
        $hint = Add-Text '' 9 $false '#66778a'
        foreach ($t in @($d.targets)) { Add-Button $footer $t | Out-Null }
        $script:viewRefresh = {
            if (-not $d.view_option) { return }
            $value = $d.options_by_key.($d.view_option).choices[$script:combos[$d.view_option].SelectedIndex].key
            $v = $d.views.$value
            if (-not $v) { return }
            $banner.Text = $v.headline.text; $banner.ForeColor = Tone $v.headline.level
            $banner.Parent.Controls[1].BackColor = Tone $v.headline.level
            Fill-Table $grid $d.columns $v.rows
            foreach ($b in $footer.Controls) {
                if ($b.Tag -and $b.Tag.target) { $b.Enabled = -not (@($v.blocked_targets) -contains $b.Tag.key) }
            }
            & $script:hintRefresh
        }
        $script:hintRefresh = {
            $off = @($footer.Controls | Where-Object { $_.Tag -and $_.Tag.target -and -not $_.Enabled }).Count
            $hint.Text = $(if ($off) { $d.blocked_hint } else { $d.ready_hint })
        }
        $f.Add_Shown({ & $script:hintRefresh })
        if ($d.view_option) { $script:combos[$d.view_option].Add_SelectedIndexChanged($script:viewRefresh); & $script:viewRefresh }
    }
    'confirm' {
        foreach ($fact in @($d.facts)) { Add-Text $fact 11 | Out-Null }
        if ($d.details) {
            $box = New-Object Windows.Forms.TextBox; $box.Multiline = $true; $box.ReadOnly = $true
            $box.Width = $width; $box.Height = 170; $box.ScrollBars = 'Vertical'; $box.Text = ($d.details -replace "`r?`n", "`r`n")
            $box.BackColor = [Drawing.Color]::White; $body.Controls.Add($box)
        }
        $script:toggles = @{}
        foreach ($t in @($d.toggles)) {
            $cb = New-Object Windows.Forms.CheckBox; $cb.Text = $t.label; $cb.Checked = [bool]$t.value
            $cb.AutoSize = $true; $cb.MaximumSize = New-Object Drawing.Size($width, 0); $cb.Margin = '0,8,0,0'
            $body.Controls.Add($cb); $script:toggles[$t.key] = $cb
            if ($t.note) { Add-Text $t.note 9 $false '#66778a' | Out-Null }
        }
        Add-Text $d.checks_label 10 $true '#a41926' | Out-Null
        $checks = New-Object Windows.Forms.CheckedListBox
        $checks.Width = $width; $checks.Height = [Math]::Min(220, 26 * @($d.checks).Count + 10); $checks.CheckOnClick = $true
        foreach ($c in @($d.checks)) { [void]$checks.Items.Add($c.label) }
        $body.Controls.Add($checks)
    }
    'progress' {
        foreach ($line in @($d.lines)) { Add-Text $line 10 | Out-Null }
        $now = Add-Text '' 13 $true '#186b96'
        $bar = New-Object Windows.Forms.ProgressBar; $bar.Width = $width; $bar.Height = 18; $bar.Style = 'Marquee'
        $body.Controls.Add($bar)
        $elapsed = Add-Text '' 10 $false '#66778a'
        $log = New-Object Windows.Forms.TextBox; $log.Multiline = $true; $log.ReadOnly = $true
        $log.Width = $width; $log.Height = 300; $log.ScrollBars = 'Vertical'; $log.Font = New-Object Drawing.Font('Malgun Gothic', 9)
        $body.Controls.Add($log)
        $started = Get-Date
        $tick = {
            if ($d.events_path -and (Test-Path -LiteralPath $d.events_path)) {
                try {
                    $stream = [IO.File]::Open($d.events_path, 'Open', 'Read', 'ReadWrite')
                    try {
                        $offset = [Math]::Max(0, $stream.Length - 65536); [void]$stream.Seek($offset, 'Begin')
                        $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)
                        try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
                    } finally { $stream.Dispose() }
                    $events = @(); foreach ($line in ($text -split "`n")) { if ($line.Trim()) { try { $events += ($line | ConvertFrom-Json) } catch {} } }
                    $shown = @($events | Select-Object -Last 20 | ForEach-Object { '{0}  {1}  {2}' -f $_.time, $_.tc_id, $_.message })
                    $log.Text = ($shown -join "`r`n")
                    $last = @($events | Where-Object { $_.total }) | Select-Object -Last 1
                    if ($last) {
                        $bar.Style = 'Continuous'; $bar.Maximum = [int]$last.total; $bar.Value = [Math]::Min([int]$last.index, [int]$last.total)
                        $now.Text = ($d.now_format -f $last.index, $last.total, $last.tc_id)
                    } elseif ($events.Count) { $now.Text = [string]$events[-1].tc_id }
                } catch {}
            }
            $elapsed.Text = ($d.elapsed_format -f ((Get-Date) - $started).ToString('hh\:mm\:ss'))
            if ($d.process_id -and -not (Get-Process -Id ([int]$d.process_id) -ErrorAction SilentlyContinue)) {
                $script:timer.Stop(); Finish-With 'finished'
            }
        }
        $script:timer = New-Object Windows.Forms.Timer; $script:timer.Interval = 700; $script:timer.Add_Tick($tick)
        $f.Add_Shown({ & $tick; $script:timer.Start() })
        $f.Add_FormClosed({ $script:timer.Stop(); $script:timer.Dispose() })
        if ($d.stop_path) {
            $stop = New-Object Windows.Forms.Button; $stop.Text = $d.stop_label; $stop.AutoSize = $true; $stop.Height = 38
            $stop.Add_Click({ [IO.File]::WriteAllText($d.stop_path, 'stop'); $this.Enabled = $false; $this.Text = $d.stop_sent_label })
            $footer.Controls.Add($stop)
        }
        if ($d.minimized -and -not $Snapshot) { $f.WindowState = 'Minimized'; $f.ShowInTaskbar = $true }
    }
    'result' {
        Add-Banner $d.headline.text $d.headline.level | Out-Null
        foreach ($line in @($d.lines)) { Add-Text $line 10 | Out-Null }
        if (@($d.rows).Count) {
            Add-Text $d.rows_label 10 $true | Out-Null
            Add-Table $d.columns $d.rows 260 | Out-Null
        }
    }
}
foreach ($b in @($d.buttons)) { Add-Button $footer $b | Out-Null }
if ($d.screen -eq 'confirm') {
    foreach ($b in $footer.Controls) {
        if ($b.Tag -and $b.Tag.primary) {
            $b.Enabled = $false; $start = $b
            $checks.Add_ItemCheck({
                param($sender, $e)
                $count = $checks.CheckedItems.Count + $(if ($e.NewValue -eq 'Checked') { 1 } else { -1 })
                $start.Enabled = ($count -eq $checks.Items.Count)
            })
        }
    }
}

if ($Snapshot) {
    $f.Add_Shown({
        $f.Refresh(); [Windows.Forms.Application]::DoEvents()
        $bmp = New-Object Drawing.Bitmap($f.Width, $f.Height)
        $f.DrawToBitmap($bmp, (New-Object Drawing.Rectangle(0, 0, $f.Width, $f.Height)))
        $bmp.Save($Snapshot, [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
        $script:answer = @{action = 'snapshot'}
        if ($script:timer) { $script:timer.Stop() }
        $f.Close()
    })
}
[void]$f.ShowDialog()
$json = $script:answer | ConvertTo-Json -Compress -Depth 6
[IO.File]::WriteAllText($Out, $json, (New-Object Text.UTF8Encoding($false)))
$f.Dispose()
