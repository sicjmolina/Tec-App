def build_email_html(nombre: str, fecha_larga: str, hora_inicio: str, ticket_id, glpi_url: str) -> str:
    hora_parts = hora_inicio.split(":")
    h_fin = str((int(hora_parts[0]) + 1) % 24).zfill(2)
    hora_rango = f"{hora_inicio} – {h_fin}:{hora_parts[1] if len(hora_parts) > 1 else '00'}"
    ticket_link = ""
    if ticket_id and glpi_url:
        url = f"{glpi_url}/front/ticket.form.php?id={ticket_id}"
        ticket_link = (
            f'<p style="margin:8px 0"><a href="{url}" style="color:#00d4ff">Ver ticket #{ticket_id} en GLPI →</a></p>'
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#111827;border-radius:12px;overflow:hidden;border:1px solid #1e2d45">
        <tr>
          <td style="background:#0a0e1a;padding:24px 32px;border-bottom:1px solid #1e2d45">
            <p style="margin:0;font-size:11px;color:#00d4ff;letter-spacing:.08em;font-family:Consolas,monospace">
              — SICOLSA — IT
            </p>
            <h1 style="margin:6px 0 0;font-size:20px;color:#ffffff;font-weight:700">
              🖥️ Mantenimiento Preventivo Programado
            </h1>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 32px">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#1a2235;border-radius:8px;border:1px solid #1e2d45">
              <tr>
                <td style="padding:20px 24px">
                  <p style="margin:0 0 4px;font-size:10px;color:#64748b;font-family:Consolas,monospace;letter-spacing:.06em">EQUIPO</p>
                  <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff">{nombre}</p>
                </td>
              </tr>
              <tr><td style="height:1px;background:#1e2d45"></td></tr>
              <tr>
                <td style="padding:16px 24px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td width="50%" style="padding-right:12px">
                        <p style="margin:0 0 4px;font-size:10px;color:#64748b;font-family:Consolas,monospace">FECHA</p>
                        <p style="margin:0;font-size:14px;color:#e2e8f0;font-weight:600">{fecha_larga.capitalize()}</p>
                      </td>
                      <td width="50%">
                        <p style="margin:0 0 4px;font-size:10px;color:#64748b;font-family:Consolas,monospace">HORA</p>
                        <p style="margin:0;font-size:14px;color:#e2e8f0;font-weight:600">{hora_rango}</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              {f'<tr><td style="height:1px;background:#1e2d45"></td></tr><tr><td style="padding:14px 24px">{ticket_link}</td></tr>' if ticket_link else ""}
            </table>
            <p style="margin:20px 0 0;font-size:13px;color:#64748b;line-height:1.6">
              Este es un aviso automático generado por la app de
              <strong style="color:#e2e8f0">Mantenimientos Preventivos — Sicolsa</strong>.
              El evento ya fue creado en el calendario de Outlook.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#0a0e1a;padding:16px 32px;border-top:1px solid #1e2d45">
            <p style="margin:0;font-size:11px;color:#64748b;font-family:Consolas,monospace">
              Sicolsa IT · Mantenimientos Preventivos v2
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
