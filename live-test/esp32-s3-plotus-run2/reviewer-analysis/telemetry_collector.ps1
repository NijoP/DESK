# READ-ONLY telemetry collector. Self-terminates after 260 minutes.
$ErrorActionPreference = 'SilentlyContinue'
$out = 'C:\nemotron test\Plotus\run2\evaluation\HARDWARE_RESOURCE_METRICS.csv'
$end = (Get-Date).AddMinutes(260)
$ncpu = [Environment]::ProcessorCount
$groups = [ordered]@{
  claude  = @('claude')
  node    = @('node')
  python  = @('python','pythonw')
  java    = @('java','javaw')
  easyeda = @('easyeda*','lceda*')
}
$hdr = @('timestamp','cpu_total_pct')
foreach ($g in $groups.Keys) { $hdr += "${g}_cpu_pct","${g}_ws_mb","${g}_private_mb","${g}_nproc" }
$hdr += 'ram_avail_mb','ram_total_mb','c_free_gb','disk_read_Bps','disk_write_Bps','net_Bps','gpu_util_pct','gpu_mem_mb','gpu_temp_c','proc_count','thread_count'
if (-not (Test-Path $out)) { ($hdr -join ',') | Out-File $out -Encoding ascii }
$prev = @{}   # pid -> @(cpuSeconds, time)
function NA($v) { if ($null -eq $v) { 'NA' } else { $v } }
$totalRam = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1MB
while ((Get-Date) -lt $end) {
  $t0 = Get-Date
  $row = @($t0.ToString('yyyy-MM-ddTHH:mm:sszzz'))
  $c = $null
  try { $c = Get-Counter '\Processor(_Total)\% Processor Time','\Memory\Available MBytes','\PhysicalDisk(_Total)\Disk Read Bytes/sec','\PhysicalDisk(_Total)\Disk Write Bytes/sec','\Network Interface(*)\Bytes Total/sec' -ErrorAction Stop } catch {}
  $cs = @{}
  if ($c) { foreach ($s in $c.CounterSamples) { $k = $s.Path; if ($k -like '*network interface*') { $cs['net'] += $s.CookedValue } else { $cs[($k -replace '^\\\\[^\\]+','')] = $s.CookedValue } } }
  $cpu = $cs['\processor(_total)\% processor time']; if ($null -ne $cpu) { $cpu = [math]::Round($cpu,1) }
  $row += (NA $cpu)
  $procs = Get-Process
  $now = Get-Date
  foreach ($g in $groups.Keys) {
    $m = $procs | Where-Object { $n = $_.Name; $groups[$g] | Where-Object { $n -like $_ } }
    $cpuS = 0.0; $ws = 0; $pv = 0; $cnt = 0
    foreach ($p in $m) {
      $cnt++; $ws += $p.WorkingSet64; $pv += $p.PrivateMemorySize64
      $tp = $p.TotalProcessorTime.TotalSeconds
      if ($prev.ContainsKey($p.Id)) { $d = $tp - $prev[$p.Id][0]; $dt = ($now - $prev[$p.Id][1]).TotalSeconds; if ($dt -gt 0 -and $d -ge 0) { $cpuS += 100 * $d / $dt / $ncpu } }
      $prev[$p.Id] = @($tp, $now)
    }
    if ($cnt -eq 0) { $row += '0','0','0','0' } else { $row += [math]::Round($cpuS,1), [math]::Round($ws/1MB,1), [math]::Round($pv/1MB,1), $cnt }
  }
  $row += (NA ($cs['\memory\available mbytes']))
  $row += [math]::Round($totalRam)
  $free = (Get-PSDrive C).Free; $row += (NA $(if ($free) { [math]::Round($free/1GB,2) }))
  foreach ($k in '\physicaldisk(_total)\disk read bytes/sec','\physicaldisk(_total)\disk write bytes/sec') { $v = $cs[$k]; $row += (NA $(if ($null -ne $v) { [math]::Round($v) })) }
  $row += (NA $(if ($null -ne $cs['net']) { [math]::Round($cs['net']) }))
  $g3 = 'NA','NA','NA'
  try { $o = & 'C:\Windows\System32\nvidia-smi.exe' '--query-gpu=utilization.gpu,memory.used,temperature.gpu' '--format=csv,noheader,nounits' 2>$null; if ($LASTEXITCODE -eq 0 -and $o) { $parts = ($o | Select-Object -First 1).Split(',') | ForEach-Object { $_.Trim() }; if ($parts.Count -eq 3) { $g3 = $parts | ForEach-Object { if ($_ -match '^\d+(\.\d+)?$') { $_ } else { 'NA' } } } } } catch {}
  $row += $g3
  $row += $procs.Count
  $th = 0; foreach ($p in $procs) { $th += $p.Threads.Count }
  $row += $th
  ($row -join ',') | Out-File $out -Append -Encoding ascii
  $sl = 60 - ((Get-Date) - $t0).TotalSeconds
  if ($sl -gt 1) { Start-Sleep -Seconds $sl }
}
