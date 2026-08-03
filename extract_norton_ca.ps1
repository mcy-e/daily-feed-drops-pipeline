$certs = Get-ChildItem -Path Cert:\LocalMachine\Root
foreach ($cert in $certs) {
    if ($cert.Subject -like '*Norton*') {
        Write-Output ("Subject: " + $cert.Subject + " | Thumbprint: " + $cert.Thumbprint)
        $pem = "-----BEGIN CERTIFICATE-----`n" + [System.Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks') + "`n-----END CERTIFICATE-----"
        $pem | Out-File -FilePath ("norton_ca.pem") -Encoding ascii
    }
}
Write-Output "Done"
