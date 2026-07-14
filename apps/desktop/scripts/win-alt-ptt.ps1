Add-Type @"
using System.Runtime.InteropServices;
public class AdeleAltKey {
    [DllImport("user32.dll")]
    public static extern short GetAsyncKeyState(int vKey);
    public static bool IsDown() {
        return (GetAsyncKeyState(0x12) & 0x8000) != 0;
    }
}
"@

$last = $false
while ($true) {
    $down = [AdeleAltKey]::IsDown()
    if ($down -ne $last) {
        if ($down) { Write-Output "DOWN" } else { Write-Output "UP" }
        $last = $down
    }
    Start-Sleep -Milliseconds 30
}
