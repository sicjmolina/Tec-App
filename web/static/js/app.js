"use strict";

// ── Estado global ─────────────────────────────────────────────────
const state = {
  modoP: false,
  equipos: [],       // candidatos actuales con fechas asignadas
  cargado: false,
  inventario: [],
  inventarioFiltrado: [],
  inventarioSel: null,
  inventarioUsuarios: [],
};

// ── Utilidades DOM ────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const setStatus = (msg, cls = "") => {
  const el = $("statusMsg");
  el.textContent = msg;
  el.className = cls ? `status-${cls}` : "";
  $("statusInline").textContent = msg;
  $("statusInline").className = `status-inline ${cls ? `status-${cls}` : ""}`;
};
const show = id => $(id).classList.remove("hidden");
const hide = id => $(id).classList.add("hidden");

// Parsea JSON de una respuesta sin explotar si el body no es JSON
async function safeJson(res) {
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    try { return await res.json(); } catch(_) {}
  }
  const text = await res.text().catch(() => "");
  return { detail: text || `Error HTTP ${res.status}` };
}

// ── Modo prueba ───────────────────────────────────────────────────
const chkPrueba = $("chkPrueba");
function syncModoPrueba() {
  state.modoP = chkPrueba.checked;
  const label  = $("togglePruebaLabel");
  const modoBar = $("modoLabel");
  if (state.modoP) {
    label.textContent        = "PRUEBA";
    label.style.color        = "";
    modoBar.style.display    = "";
  } else {
    label.textContent        = "REAL";
    label.style.color        = "var(--success)";
    modoBar.style.display    = "none";
  }
}
chkPrueba.addEventListener("change", syncModoPrueba);
syncModoPrueba();

// ── Cargar equipos ────────────────────────────────────────────────
$("btnCargar").addEventListener("click", async () => {
  $("btnCargar").disabled = true;
  $("btnCargar").innerHTML = `<span class="spinner"></span>Cargando...`;
  $("btnConfirmar").disabled = true;
  setStatus("Conectando con GLPI...", "accent");

  try {
    const res = await fetch(`/api/cargar?modo_prueba=${state.modoP}`);
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Error del servidor (${res.status})`);
    }
    const data = await res.json();
    renderDashboard(data);
    setStatus(`✓ ${data.candidatos.length} equipos cargados${state.modoP ? " [PRUEBA]" : ""}`, "success");
  } catch (e) {
    setStatus(`✗ ${e.message}`, "danger");
    alert("Error al cargar equipos:\n" + e.message);
  } finally {
    $("btnCargar").disabled = false;
    $("btnCargar").textContent = "▶ Cargar equipos desde GLPI";
  }
});

// ── Render principal ──────────────────────────────────────────────
function renderDashboard(data) {
  state.cargado = true;
  renderMesAnterior(data.tickets_ant);
  renderMesActual(data);
  // Badge "ya hecho"
  if (data.mes_actual_done) {
    $("badgeDone").textContent = "✓ Tickets del mes ya creados";
  } else {
    $("badgeDone").textContent = "";
  }
}

// ── Panel mes anterior ────────────────────────────────────────────
function renderMesAnterior(ant) {
  const panel = $("panelAnterior");
  panel.innerHTML = "";

  // Título
  const hoy   = new Date();
  const meses = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
  let y = hoy.getFullYear(), m = hoy.getMonth(); // getMonth() = 0-based
  if (m === 0) { y--; m = 12; }

  const title = document.createElement("p");
  title.className = "section-label";
  title.textContent = `MES ANTERIOR — ${meses[m].toUpperCase()} ${y}`;
  panel.appendChild(title);

  if (!ant || ant.items.length === 0) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "No se encontraron tickets del mes anterior.";
    panel.appendChild(p);
    return;
  }

  // Summary boxes
  const summary = document.createElement("div");
  summary.className = "ant-summary";
  summary.innerHTML = `
    <div class="stat-box" style="border:1px solid var(--success)">
      <div class="stat-num" style="color:var(--success)">${ant.completados}</div>
      <div class="stat-lbl">COMPLETADOS</div>
    </div>
    <div class="stat-box" style="border:1px solid ${ant.pendientes ? "var(--warning)" : "var(--border)"}">
      <div class="stat-num" style="color:${ant.pendientes ? "var(--warning)" : "var(--muted)"}">${ant.pendientes}</div>
      <div class="stat-lbl">PENDIENTES</div>
    </div>`;
  panel.appendChild(summary);

  // Rows
  for (const t of ant.items) {
    let icon, color;
    if ([5,6].includes(t.status_glpi))   { icon = "✓"; color = "var(--success)"; }
    else if (t.status_glpi)              { icon = "●"; color = "var(--warning)"; }
    else                                 { icon = "?"; color = "var(--muted)"; }

    const row = document.createElement("div");
    row.className = "ant-row";
    row.innerHTML = `
      <span class="ant-icon" style="color:${color}">${icon}</span>
      <span class="ant-nombre" style="color:${[5,6].includes(t.status_glpi) ? "var(--muted)" : "var(--white)"}">${esc(t.nombre)}</span>
      ${t.fecha ? `<span class="ant-fecha">${esc(t.fecha)}</span>` : ""}`;
    panel.appendChild(row);
  }

  // Alerta pendientes
  if (ant.pendientes > 0) {
    const alert = document.createElement("div");
    alert.className = "alert-pendientes";
    alert.textContent = `⚠  ${ant.pendientes} ticket(s) del mes anterior sin cerrar — considera priorizarlos`;
    panel.appendChild(alert);
  }
}

// ── Panel mes actual ──────────────────────────────────────────────
function renderMesActual(data) {
  // Label
  const hoy   = new Date();
  const meses = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
  $("labelMesActual").textContent =
    `MES ACTUAL — ${meses[hoy.getMonth()+1].toUpperCase()} ${hoy.getFullYear()}`;

  // ── Cuota stats visuales
  const stats = $("cuotaStats");
  stats.classList.remove("hidden");
  $("cstatTotal").querySelector(".cuota-stat-num").textContent    = data.total;
  $("cstatCuota").querySelector(".cuota-stat-num").textContent    = data.cuota;
  $("cstatTickets").querySelector(".cuota-stat-num").textContent  = data.ya_tienen || 0;
  $("cstatPendientes").querySelector(".cuota-stat-num").textContent = data.candidatos.length;
  // Color dinámico de pendientes
  const numPend = $("cstatPendientes").querySelector(".cuota-stat-num");
  numPend.style.color = data.candidatos.length > 0 ? "var(--warning)" : "var(--success)";

  const list = $("equiposList");
  list.innerHTML = "";
  state.equipos = [];

  // ── Ya creados este mes
  if (data.tickets_mes.length > 0) {
    const secTitle = document.createElement("p");
    secTitle.className = "sec-title";
    secTitle.textContent = `YA CREADOS ESTE MES (${data.tickets_mes.length})`;
    list.appendChild(secTitle);

    const STATUS_COLOR = {1:"var(--muted)",2:"var(--accent)",3:"var(--warning)",
                          4:"var(--warning)",5:"var(--success)",6:"var(--success)"};

    for (const t of data.tickets_mes) {
      const color    = STATUS_COLOR[t.status_id] || "var(--muted)";
      const hoy_d    = new Date().toISOString().slice(0,10);
      const vencida  = t.fecha_limite && t.fecha_limite !== "—" && t.fecha_limite < hoy_d;
      const limiteTxt = t.fecha_limite && t.fecha_limite !== "—"
        ? `límite: ${t.fecha_limite}` : "";
      const yaCerrado = [5, 6].includes(t.status_id);

      const row = document.createElement("div");
      row.className = `ticket-row${yaCerrado ? " done" : ""}${vencida && !yaCerrado ? " vencida-row" : ""}`;
      row.dataset.ticketId = t.id;
      row.dataset.nombre   = t.nombre;

      const completarTxt = vencida && !yaCerrado ? "⚠ Completar (vencida)" : "✓ Completar";

      row.innerHTML = `
        <span class="ticket-dot" style="color:${color}">●</span>
        <span class="ticket-nombre" title="${esc(t.nombre)}">${esc(t.nombre)}</span>
        <span class="ticket-status" style="color:${color}">${esc(t.status_txt)}</span>
        ${limiteTxt ? `<span class="ticket-limit ${vencida ? "vencida" : ""}">${esc(limiteTxt)}</span>` : ""}
        ${yaCerrado
          ? `<span class="ticket-done-badge">✓ Completado</span>`
          : `<button class="btn-completar" data-id="${t.id}" data-nombre="${esc(t.nombre)}">${completarTxt}</button>`
        }`;

      if (!yaCerrado) {
        row.querySelector(".btn-completar").addEventListener("click", () => {
          abrirChecklist({ ticket_id: t.id, nombre: t.nombre, rowEl: row });
        });
      }

      list.appendChild(row);
    }

    const sep = document.createElement("div"); sep.className = "sec-sep"; list.appendChild(sep);
  }

  // ── Candidatos pendientes
  if (data.candidatos.length === 0) {
    const msg = document.createElement("p");
    msg.style.cssText = "color:var(--muted);font-size:13px;padding:20px 0;text-align:center";
    msg.textContent = data.tickets_mes.length > 0
      ? "TODOS LOS EQUIPOS YA TIENEN TICKET ESTE MES"
      : "No hay equipos pendientes de mantenimiento este mes.";
    list.appendChild(msg);
    $("btnConfirmar").disabled = true;
    return;
  }

  const secPend = document.createElement("p");
  secPend.className = "sec-title";
  secPend.textContent = `PENDIENTES DE CREAR (${data.candidatos.length})`;
  list.appendChild(secPend);

  for (let i = 0; i < data.candidatos.length; i++) {
    const eq  = data.candidatos[i];
    const row = buildEquipoRow(i, eq);
    list.appendChild(row.el);
    state.equipos.push(row);
  }

  $("btnConfirmar").disabled = false;
  $("btnConfirmar").className = "btn btn-success";
}

// ── Equipo row editable ───────────────────────────────────────────
function buildEquipoRow(idx, eq) {
  const el = document.createElement("div");
  el.className = "equipo-row";
  el.dataset.idx = idx;

  const sinHistorial = !eq.ultima_fecha || eq.ultima_fecha.startsWith("1990");
  if (sinHistorial) el.classList.add("sin-historial");

  el.innerHTML = `
    <input type="checkbox" checked title="Incluir"/>
    <div class="equipo-info">
      <span class="equipo-idx">EQUIPO ${String(idx+1).padStart(2,"0")}</span>
      <div class="equipo-nombre">
        ${esc(eq.nombre)}
        ${sinHistorial ? `<span class="badge-sin-registro" title="Sin mantenimiento registrado en GLPI">SIN REGISTRO</span>` : ""}
      </div>
      ${!sinHistorial && eq.ultima_fecha
        ? `<div class="equipo-ultima">Último mant.: ${eq.ultima_fecha}</div>`
        : sinHistorial ? `<div class="equipo-ultima" style="color:var(--warning)">Sin mantenimiento previo registrado</div>` : ""}
      <div class="dest-wrap">
        <span class="dest-icon">✉</span>
        <input type="text" class="inp-dest"
               placeholder="Destinatarios: correo1@empresa.com, correo2@empresa.com"
               title="Emails a notificar de este mantenimiento (separados por coma)"/>
      </div>
    </div>
    <div class="equipo-controls">
      <div class="ctrl-group">
        <label>Fecha límite</label>
        <input type="date" class="inp-fecha" value="${eq.fecha_limite || ""}"/>
      </div>
      <div class="ctrl-group">
        <label>Hora inicio</label>
        <input type="time" class="inp-hora" value="08:00"/>
        <span class="hint">+1 hora</span>
      </div>
    </div>`;

  const chk  = el.querySelector("input[type=checkbox]");
  chk.addEventListener("change", () => {
    el.classList.toggle("excluido", !chk.checked);
  });

  // Validación visual de fecha
  const inpFecha = el.querySelector(".inp-fecha");
  inpFecha.addEventListener("change", () => {
    inpFecha.style.borderColor = inpFecha.value ? "" : "var(--danger)";
  });

  return {
    el,
    getData() {
      return {
        id:            eq.id,
        nombre:        eq.nombre,
        fecha_limite:  inpFecha.value,
        hora_inicio:   el.querySelector(".inp-hora").value || "08:00",
        incluido:      chk.checked,
        destinatarios: el.querySelector(".inp-dest").value.trim(),
      };
    },
  };
}

// ── Confirmar ─────────────────────────────────────────────────────
$("btnConfirmar").addEventListener("click", () => {
  if (!state.cargado) return;

  // Validar fechas
  const invalidas = state.equipos
    .filter(r => r.getData().incluido && !r.getData().fecha_limite);
  if (invalidas.length > 0) {
    alert(`Hay ${invalidas.length} equipo(s) sin fecha límite. Asígnala antes de continuar.`);
    return;
  }

  openConfirm(
    state.modoP ? "Simulación (modo prueba)" : "Crear tickets y eventos",
    state.modoP
      ? "Se simularán los tickets sin hacer cambios reales en GLPI ni Outlook. ¿Continuar?"
      : "Se crearán tickets en GLPI y eventos en Outlook. Esta acción es real. ¿Continuar?",
    ejecutarConfirmar
  );
});

async function ejecutarConfirmar() {
  $("btnConfirmar").disabled = true;
  $("btnConfirmar").innerHTML = `<span class="spinner"></span>Procesando...`;
  setStatus("Procesando...", "accent");

  const payload = {
    modo_prueba: state.modoP,
    equipos: state.equipos.map(r => r.getData()),
  };

  try {
    const res = await fetch("/api/confirmar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Error del servidor (${res.status})`);
    }
    const data = await res.json();
    renderResultado(data);
    setStatus(
      data.ok
        ? `✓ ${data.creados.length} ${state.modoP ? "simulados" : "creados en GLPI + Outlook"}`
        : `⚠ ${data.errores.length} errores`,
      data.ok ? "success" : "danger"
    );
  } catch (e) {
    setStatus(`✗ ${e.message}`, "danger");
    alert("Error al confirmar:\n" + e.message);
  } finally {
    $("btnConfirmar").disabled = false;
    $("btnConfirmar").innerHTML = "✓ Crear tickets y eventos en Outlook";
    $("btnConfirmar").className = "btn btn-success";
  }
}

// ── Modal resultado ───────────────────────────────────────────────
function renderResultado(data) {
  const titulo = data.ok
    ? `✓ Listo${state.modoP ? " [PRUEBA]" : ""} — ${data.creados.length} mantenimientos`
    : `⚠ Completado con errores — ${data.creados.length} ok / ${data.errores.length} fallidos`;
  $("resultTitle").textContent = titulo;

  const body = $("resultBody");
  body.innerHTML = "";

  for (const c of data.creados) {
    const d = document.createElement("div");
    d.className = "result-item";
    const extras = [
      c.ticket_id  ? `ticket #${c.ticket_id}` : "",
      c.evento_id && !c.evento_id.startsWith("fake") ? "📅 evento creado" : "",
      c.correo_ok  ? "✉️ correo enviado" : "",
    ].filter(Boolean).join(" · ");
    d.innerHTML = `
      <span class="result-icon" style="color:var(--success)">✓</span>
      <div class="result-detail">
        <strong>${esc(c.nombre)}</strong>
        <small>${esc(c.fecha)}${extras ? ` · ${extras}` : ""}</small>
      </div>`;
    body.appendChild(d);
  }
  for (const e of data.errores) {
    const d = document.createElement("div");
    d.className = "result-item";
    d.innerHTML = `
      <span class="result-icon" style="color:var(--danger)">✗</span>
      <div class="result-detail"><strong style="color:var(--danger)">${esc(e)}</strong></div>`;
    body.appendChild(d);
  }

  show("modalResult");

  // Recargar badge
  if (data.ok) {
    $("badgeDone").textContent = "✓ Tickets del mes ya creados";
  }
}

// ── Config modal ──────────────────────────────────────────────────
$("btnConfig").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    populateConfig(cfg);
    renderCalendarPicker(_outlookCalendars, $("cfg_outlook_calendar_id").value.trim());
    renderCalendarsDebugList([]);
  } catch(e) { /* silencioso */ }
  show("modalConfig");
});

const PLACEHOLDER = "__saved__";
const SECRET_FIELDS = new Set(["cfg_glpi_app_token","cfg_glpi_user_token","cfg_azure_client_secret"]);
let _outlookCalendars = [];

function getConfigBody() {
  return {
    glpi_url:            $("cfg_glpi_url").value.trim(),
    glpi_app_token:      $("cfg_glpi_app_token").value.trim(),
    glpi_user_token:     $("cfg_glpi_user_token").value.trim(),
    glpi_category_id:    $("cfg_glpi_category_id").value.trim() || "22",
    glpi_field_id:       $("cfg_glpi_field_id").value.trim() || "76670",
    azure_client_id:     $("cfg_azure_client_id").value.trim(),
    azure_client_secret: $("cfg_azure_client_secret").value.trim(),
    azure_tenant_id:     $("cfg_azure_tenant_id").value.trim(),
    outlook_calendar_id: $("cfg_outlook_calendar_id").value.trim(),
    outlook_user_upn:    $("cfg_outlook_user_upn").value.trim(),
    notify_emails:       $("cfg_notify_emails").value.trim(),
  };
}

function renderCalendarPicker(calendars = [], selectedId = "") {
  const pick = $("cfg_outlook_calendar_pick");
  if (!pick) return;
  pick.innerHTML = "";

  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "— Selecciona un calendario —";
  pick.appendChild(empty);

  for (const cal of calendars) {
    if (!cal?.id) continue;
    const opt = document.createElement("option");
    opt.value = cal.id;
    opt.textContent = cal.name ? `${cal.name} — ${cal.id.slice(0, 18)}...` : cal.id;
    pick.appendChild(opt);
  }
  pick.value = selectedId || "";
}

function renderCalendarsDebugList(calendars = []) {
  const wrap = $("testOutlookCalendars");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!calendars.length) return;

  const title = document.createElement("div");
  title.innerHTML = `<strong style="color:var(--text)">Calendarios disponibles</strong> (clic para copiar ID):`;
  wrap.appendChild(title);

  const ul = document.createElement("ul");
  ul.style.cssText = "margin:6px 0 0 14px;list-style:disc";
  for (const c of calendars) {
    const li = document.createElement("li");
    li.style.cssText = "margin-bottom:4px;line-height:1.4";

    const name = document.createElement("strong");
    name.style.color = "var(--text)";
    name.textContent = c.name || "(sin nombre)";

    const idBtn = document.createElement("button");
    idBtn.type = "button";
    idBtn.className = "btn-link";
    idBtn.style.cssText = "display:block;margin-top:2px;font-family:var(--mono);font-size:10px;color:var(--accent);word-break:break-all;background:none;border:none;padding:0;text-align:left;cursor:pointer";
    idBtn.textContent = c.id || "";
    idBtn.title = "Clic para copiar";
    idBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(c.id || "");
        idBtn.textContent = "¡Copiado!";
        setTimeout(() => { idBtn.textContent = c.id || ""; }, 1200);
      } catch (_) {}
    });

    li.appendChild(name);
    li.appendChild(idBtn);
    ul.appendChild(li);
  }
  wrap.appendChild(ul);
}

function populateConfig(cfg) {
  const map = {
    glpi_url:            "cfg_glpi_url",
    glpi_app_token:      "cfg_glpi_app_token",
    glpi_user_token:     "cfg_glpi_user_token",
    glpi_category_id:    "cfg_glpi_category_id",
    glpi_field_id:       "cfg_glpi_field_id",
    azure_client_id:     "cfg_azure_client_id",
    azure_client_secret: "cfg_azure_client_secret",
    azure_tenant_id:     "cfg_azure_tenant_id",
    outlook_calendar_id: "cfg_outlook_calendar_id",
    outlook_user_upn:    "cfg_outlook_user_upn",
    notify_emails:       "cfg_notify_emails",
  };
  for (const [key, elId] of Object.entries(map)) {
    const el = $(elId);
    if (!el || cfg[key] === undefined) continue;

    if (cfg[key] === PLACEHOLDER) {
      // Campo secreto con valor guardado: mostrar placeholder visual
      el.value = PLACEHOLDER;
      el.dataset.hasSaved = "1";
      el.placeholder = "Valor guardado — escribe para cambiar";
      // Al enfocar, limpiar para que el usuario pueda escribir el nuevo valor
      if (!el.dataset.placeholderBound) {
        el.dataset.placeholderBound = "1";
        el.addEventListener("focus", () => {
          if (el.value === PLACEHOLDER) { el.value = ""; el.placeholder = "Nuevo valor (dejar vacío para mantener el actual)"; }
        });
        el.addEventListener("blur", () => {
          if (el.value === "" && el.dataset.hasSaved === "1") {
            el.value = PLACEHOLDER; el.placeholder = "Valor guardado — escribe para cambiar";
          }
        });
      }
    } else {
      el.value = cfg[key];
    }
  }
}

$("btnSaveConfig").addEventListener("click", async () => {
  const body = getConfigBody();
  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    hide("modalConfig");
    setStatus("Configuración guardada", "success");
  } catch(e) {
    alert("Error al guardar config:\n" + e.message);
  }
});

// ── Probar conexión Outlook ───────────────────────────────────────
$("btnTestOutlook").addEventListener("click", async () => {
  const el = $("testOutlookResult");
  $("btnTestOutlook").disabled = true;
  $("btnTestOutlook").innerHTML = `<span class="spinner"></span>Probando...`;
  el.textContent = "";
  el.style.color = "var(--muted)";
  renderCalendarsDebugList([]);
  renderCalendarPicker(_outlookCalendars, $("cfg_outlook_calendar_id").value.trim());

  // Guardar config actual primero
  const body = getConfigBody();
  await fetch("/api/config", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body) });

  try {
    const res  = await fetch("/api/test-outlook");
    const data = await res.json();
    if (data.ok) {
      let msg = `✓ ${data.mensaje}`;
      el.style.color = data.cal_warning ? "var(--warning)" : "var(--success)";
      el.textContent = msg;
      _outlookCalendars = data.calendarios_disponibles || [];
      renderCalendarPicker(_outlookCalendars, $("cfg_outlook_calendar_id").value.trim());
      renderCalendarsDebugList(_outlookCalendars);
    } else {
      el.textContent = `✗ [${data.step}] ${data.error}`;
      el.style.color = "var(--danger)";
    }
  } catch(e) {
    el.textContent = `✗ ${e.message}`;
    el.style.color = "var(--danger)";
  } finally {
    $("btnTestOutlook").disabled = false;
    $("btnTestOutlook").textContent = "⚡ Probar conexión Outlook";
  }
});

$("btnTestOutlookEvent").addEventListener("click", async () => {
  const el = $("testOutlookResult");
  const btn = $("btnTestOutlookEvent");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>Probando evento...`;
  el.textContent = "";
  el.style.color = "var(--muted)";

  // Persistir cambios antes de probar
  const body = getConfigBody();
  await fetch("/api/config", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body) });

  try {
    const res = await fetch("/api/test-outlook-event", { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      el.textContent = `✓ ${data.mensaje}`;
      el.style.color = "var(--success)";
    } else {
      el.textContent = `✗ [${data.step}] ${data.error}`;
      el.style.color = "var(--danger)";
    }
  } catch (e) {
    el.textContent = `✗ ${e.message}`;
    el.style.color = "var(--danger)";
  } finally {
    btn.disabled = false;
    btn.textContent = "🧪 Probar crear/eliminar evento";
  }
});

$("cfg_outlook_calendar_pick").addEventListener("change", () => {
  const val = $("cfg_outlook_calendar_pick").value;
  if (!val) return;
  $("cfg_outlook_calendar_id").value = val;
});

$("btnCloseConfig").addEventListener("click",  () => hide("modalConfig"));
$("btnCancelConfig").addEventListener("click", () => hide("modalConfig"));

// ── Inventario de activos ────────────────────────────────────────
$("btnInventario").addEventListener("click", async () => {
  await cargarInventario();
  show("modalInventario");
});

$("btnCloseInventario").addEventListener("click", () => hide("modalInventario"));
$("btnInvRefresh").addEventListener("click", async () => { await cargarInventario(); });
$("invSearch").addEventListener("input", () => aplicarFiltroInventario());
$("btnInvGuardar").addEventListener("click", async () => { await guardarMovimientoInventario(); });
$("invTipo").addEventListener("change", () => syncEstadoNuevoConTipo(false));

function syncEstadoNuevoConTipo(forceBase = false) {
  const tipo = $("invTipo").value;
  const estadoInp = $("invEstadoNuevo");
  if (tipo === "desactivacion") {
    estadoInp.value = "Inactivo";
    return;
  }
  if (tipo === "baja") {
    estadoInp.value = "Baja";
    return;
  }
  if (tipo === "reactivacion") {
    estadoInp.value = "Activo";
    return;
  }
  if (forceBase) {
    estadoInp.value = state.inventarioSel?.estado_actual || "";
  }
}

async function cargarInventario() {
  const list = $("invList");
  const resumen = $("invResumen");
  list.innerHTML = `<p class="muted">Cargando activos...</p>`;
  resumen.textContent = "Conectando...";
  try {
    const [resActivos, resUsuarios] = await Promise.all([
      fetch(`/api/inventario/activos?modo_prueba=${state.modoP}`),
      fetch(`/api/inventario/usuarios?modo_prueba=${state.modoP}`),
    ]);
    if (!resActivos.ok) {
      const err = await safeJson(resActivos);
      throw new Error(err?.detail || `Error HTTP ${resActivos.status}`);
    }
    if (!resUsuarios.ok) {
      const err = await safeJson(resUsuarios);
      throw new Error(err?.detail || `Error HTTP ${resUsuarios.status}`);
    }
    const dataActivos = await resActivos.json();
    const dataUsuarios = await resUsuarios.json();
    state.inventario = dataActivos.items || [];
    state.inventarioUsuarios = dataUsuarios.items || [];
    renderUsuariosInventarioSelects();
    state.inventarioSel = null;
    limpiarFormInventario();
    aplicarFiltroInventario();
  } catch (e) {
    list.innerHTML = `<p class="muted" style="color:var(--danger)">Error: ${esc(e.message)}</p>`;
    resumen.textContent = "Error al cargar.";
  }
}

function renderUsuariosInventarioSelects() {
  const prev = $("invUsuarioAnterior");
  const next = $("invUsuarioNuevo");
  const options = [`<option value="">— Selecciona usuario —</option>`];
  for (const u of state.inventarioUsuarios) {
    options.push(`<option value="${esc(u.id)}">${esc(`${u.nombre} (#${u.id})`)}</option>`);
  }
  const html = options.join("");
  prev.innerHTML = html;
  next.innerHTML = html;
}

function ensureSelectValue(selectId, value) {
  const val = String(value || "").trim();
  const sel = $(selectId);
  if (!val) {
    sel.value = "";
    return;
  }
  const exists = Array.from(sel.options).some(o => o.value === val);
  if (!exists) {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = `ID ${val} (no listado)`;
    sel.appendChild(opt);
  }
  sel.value = val;
}

function aplicarFiltroInventario() {
  const q = $("invSearch").value.trim().toLowerCase();
  const base = state.inventario || [];
  state.inventarioFiltrado = !q ? base : base.filter(a => {
    const txt = `${a.nombre || ""} ${a.serial || ""} ${a.asset_id || ""}`.toLowerCase();
    return txt.includes(q);
  });
  renderInventarioLista();
}

function renderInventarioLista() {
  const list = $("invList");
  const total = state.inventario.length;
  const bajas = state.inventario.filter(a => a.baja).length;
  $("invResumen").textContent = `Total: ${total} · Bajas: ${bajas} · Activos: ${total - bajas}`;

  list.innerHTML = "";
  if (!state.inventarioFiltrado.length) {
    list.innerHTML = `<p class="muted">No hay activos para mostrar.</p>`;
    return;
  }

  for (const a of state.inventarioFiltrado) {
    const row = document.createElement("div");
    row.className = `inv-row${state.inventarioSel?.asset_id === a.asset_id ? " selected" : ""}`;
    row.innerHTML = `
      <div class="inv-row-title">
        ${esc(a.nombre || "Sin nombre")}
        ${a.baja ? `<span class="inv-badge-baja">BAJA</span>` : ""}
      </div>
      <div class="inv-row-meta">
        ID: ${esc(a.asset_id || "—")} · Serial: ${esc(a.serial || "—")} · Usuario: ${esc(a.usuario_actual || "—")} · Estado: ${esc(a.estado_actual || "—")}
      </div>`;
    row.addEventListener("click", async () => {
      state.inventarioSel = a;
      $("invAssetInfo").value = `${a.nombre || "Sin nombre"} (ID: ${a.asset_id || "—"})`;
      ensureSelectValue("invUsuarioAnterior", a.usuario_actual || "");
      syncEstadoNuevoConTipo(true);
      renderInventarioLista();
      await cargarHistorialInventario(a.asset_id);
    });
    list.appendChild(row);
  }
}

async function cargarHistorialInventario(assetId) {
  const box = $("invHistory");
  box.innerHTML = `<p class="muted">Cargando historial...</p>`;
  try {
    const res = await fetch(`/api/inventario/historial?asset_id=${encodeURIComponent(assetId)}`);
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Error HTTP ${res.status}`);
    }
    const data = await res.json();
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = `<p class="muted">Sin movimientos registrados para este activo.</p>`;
      return;
    }
    box.innerHTML = "";
    for (const m of items) {
      const el = document.createElement("div");
      el.className = "inv-history-item";
      const lineaUsuarios = [m.usuario_anterior, m.usuario_nuevo].filter(Boolean).join(" → ");
      el.innerHTML = `
        <div class="inv-history-top">${esc((m.tipo || "").toUpperCase())} ${lineaUsuarios ? `· ${esc(lineaUsuarios)}` : ""}</div>
        <div class="inv-history-meta">${esc(m.fecha || "")} · ${esc(m.responsable || "sin responsable")} ${m.ticket_id ? `· ticket ${esc(m.ticket_id)}` : ""} ${m.motivo ? `· ${esc(m.motivo)}` : ""}</div>`;
      box.appendChild(el);
    }
  } catch (e) {
    box.innerHTML = `<p class="muted" style="color:var(--danger)">Error: ${esc(e.message)}</p>`;
  }
}

async function guardarMovimientoInventario() {
  const a = state.inventarioSel;
  if (!a) {
    alert("Selecciona primero un activo.");
    return;
  }
  const payload = {
    asset_id: a.asset_id || "",
    asset_nombre: a.nombre || "",
    tipo: $("invTipo").value,
    usuario_anterior: $("invUsuarioAnterior").value.trim(),
    usuario_nuevo: $("invUsuarioNuevo").value.trim(),
    estado_nuevo: $("invEstadoNuevo").value.trim(),
    motivo: $("invMotivo").value.trim(),
    responsable: $("invResponsable").value.trim(),
    ticket_id: $("invTicketId").value.trim(),
    fecha: "",
    modo_prueba: state.modoP,
  };
  try {
    const res = await fetch("/api/inventario/movimiento", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Error HTTP ${res.status}`);
    }
    const data = await res.json();
    const syncTxt = data?.glpi_sync?.ok
      ? " y sincronizado con GLPI"
      : (state.modoP ? " [PRUEBA]" : "");
    mostrarToast(`✓ Movimiento guardado para ${a.nombre}${syncTxt}`);
    await cargarInventario();
    state.inventarioSel = (state.inventario || []).find(x => x.asset_id === a.asset_id) || null;
    if (state.inventarioSel) {
      $("invAssetInfo").value = `${state.inventarioSel.nombre || "Sin nombre"} (ID: ${state.inventarioSel.asset_id || "—"})`;
      await cargarHistorialInventario(state.inventarioSel.asset_id);
    }
    limpiarFormInventario(false);
  } catch (e) {
    alert("Error al guardar movimiento:\n" + e.message);
  }
}

function limpiarFormInventario(resetSeleccion = true) {
  if (resetSeleccion) $("invAssetInfo").value = "";
  $("invTipo").value = "asignacion";
  ensureSelectValue("invUsuarioAnterior", "");
  ensureSelectValue("invUsuarioNuevo", "");
  syncEstadoNuevoConTipo(true);
  $("invMotivo").value = "";
  $("invResponsable").value = "";
  $("invTicketId").value = "";
  $("invHistory").innerHTML = `<p class="muted">Selecciona un activo para ver su historial.</p>`;
}

// ── Tabs config ───────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    $("tabGlpi").classList.toggle("hidden",  tab !== "glpi");
    $("tabAzure").classList.toggle("hidden", tab !== "azure");
  });
});

// ── Modal confirm genérico ────────────────────────────────────────
let _confirmCb = null;
function openConfirm(title, msg, cb) {
  $("modalConfTitle").textContent = title;
  $("modalConfMsg").textContent   = msg;
  _confirmCb = cb;
  show("modalConfirmar");
}
$("btnConfYes").addEventListener("click", () => {
  hide("modalConfirmar");
  if (_confirmCb) _confirmCb();
});
$("btnConfNo").addEventListener("click",  () => hide("modalConfirmar"));

// ── Modal resultado close ─────────────────────────────────────────
$("btnCloseResult").addEventListener("click",  () => hide("modalResult"));
$("btnCloseResult2").addEventListener("click", () => hide("modalResult"));

// ── Cerrar modales clicando backdrop ─────────────────────────────
["modalConfig","modalConfirmar","modalResult","modalInventario"].forEach(id => {
  $(id).addEventListener("click", e => {
    if (e.target === $(id)) hide(id);
  });
});

// ── Escape cierra modales ─────────────────────────────────────────
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    ["modalConfig","modalConfirmar","modalResult","modalInventario"].forEach(hide);
  }
});

// ── Escape HTML ──────────────────────────────────────────────────
function esc(str) {
  return String(str ?? "")
    .replace(/&/g,"&amp;")
    .replace(/</g,"&lt;")
    .replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;");
}

// ══════════════════════════════════════════════════════════════════
// CHECKLIST
// ══════════════════════════════════════════════════════════════════

// Contexto del checklist abierto actualmente
let _ckCtx = null;  // { ticket_id, nombre, computer_id, rowEl }
let _ckItems = [];  // lista de items del servidor

async function abrirChecklist({ ticket_id, nombre, computer_id = null, rowEl }) {
  _ckCtx = { ticket_id, nombre, computer_id, rowEl };

  // Cargar checklist desde API (una sola vez, luego queda en _ckItems)
  if (_ckItems.length === 0) {
    try {
      const res = await fetch("/api/checklist");
      _ckItems = await res.json();
    } catch(e) {
      alert("Error cargando checklist: " + e.message);
      return;
    }
  }

  // Título
  $("checklistTitle").textContent    = `Mantenimiento Preventivo`;
  $("checklistSubtitle").textContent = nombre;
  $("checklistNotas").value          = "";
  $("btnSubmitChecklist").disabled   = true;

  // Renderizar items agrupados por categoría
  const body = $("checklistBody");
  body.innerHTML = "";

  let catActual = null;
  for (const item of _ckItems) {
    if (item.categoria !== catActual) {
      catActual = item.categoria;
      const h = document.createElement("div");
      h.className = "check-cat-title";
      h.textContent = item.categoria;
      body.appendChild(h);
    }

    const wrap = document.createElement("div");
    wrap.className = "check-item";
    wrap.dataset.id = item.id;

    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.id   = `ck_${item.id}`;
    chk.addEventListener("change", actualizarProgreso);

    const lbl = document.createElement("label");
    lbl.htmlFor     = `ck_${item.id}`;
    lbl.textContent = item.texto;

    wrap.appendChild(chk);
    wrap.appendChild(lbl);
    wrap.addEventListener("click", e => {
      if (e.target !== chk) { chk.checked = !chk.checked; actualizarProgreso(); }
    });

    body.appendChild(wrap);
  }

  actualizarProgreso();
  show("modalChecklist");
}

function actualizarProgreso() {
  const total   = _ckItems.length;
  const marcados = $("checklistBody")
    .querySelectorAll("input[type=checkbox]:checked").length;
  const pct = total > 0 ? (marcados / total) * 100 : 0;

  $("checkProgressFill").style.width  = pct + "%";
  $("checkProgressLabel").textContent = `${marcados} / ${total}`;

  // Tachar items marcados
  $("checklistBody").querySelectorAll(".check-item").forEach(w => {
    const chk = w.querySelector("input");
    w.classList.toggle("checked", chk.checked);
  });

  // Habilitar confirmar si al menos hay 1 marcado
  $("btnSubmitChecklist").disabled = marcados === 0;

  // Color de progreso
  const fill = $("checkProgressFill");
  if (pct === 100)     fill.style.background = "var(--success)";
  else if (pct >= 60)  fill.style.background = "var(--warning)";
  else                 fill.style.background = "var(--accent)";
}

// Marcar todo
$("btnCheckAll").addEventListener("click", () => {
  $("checklistBody").querySelectorAll("input[type=checkbox]").forEach(c => c.checked = true);
  actualizarProgreso();
});

// Cerrar sin confirmar
$("btnCloseChecklist").addEventListener("click",  () => hide("modalChecklist"));
$("btnCancelChecklist").addEventListener("click", () => hide("modalChecklist"));

// Confirmar checklist → llamar API
$("btnSubmitChecklist").addEventListener("click", async () => {
  if (!_ckCtx) return;

  const items_ok = [];
  $("checklistBody").querySelectorAll("input[type=checkbox]:checked").forEach(c => {
    const wrap = c.closest(".check-item");
    if (wrap) items_ok.push(wrap.dataset.id);
  });

  const notas = $("checklistNotas").value.trim();
  const total  = _ckItems.length;

  // Confirmar si hay items sin marcar
  if (items_ok.length < total) {
    const faltantes = total - items_ok.length;
    const ok = confirm(
      `Hay ${faltantes} ítem(s) sin marcar.\n¿Confirmar de todas formas y cerrar el ticket?`
    );
    if (!ok) return;
  }

  $("btnSubmitChecklist").disabled = true;
  $("btnSubmitChecklist").innerHTML = `<span class="spinner"></span>Guardando...`;

  try {
    const res = await fetch("/api/completar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticket_id:   _ckCtx.ticket_id,
        computer_id: _ckCtx.computer_id ?? null,
        nombre:      _ckCtx.nombre,
        items_ok,
        notas,
        modo_prueba: state.modoP,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || res.statusText);
    }

    const data = await res.json();
    hide("modalChecklist");

    // Actualizar la fila en la UI
    if (_ckCtx.rowEl) {
      const row = _ckCtx.rowEl;
      row.classList.add("done");
      const btnComp = row.querySelector(".btn-completar");
      if (btnComp) btnComp.replaceWith((() => {
        const b = document.createElement("span");
        b.className   = "ticket-done-badge";
        b.textContent = "✓ Completado";
        return b;
      })());
      // Actualizar dot y status a verde
      const dot    = row.querySelector(".ticket-dot");
      const status = row.querySelector(".ticket-status");
      if (dot)    dot.style.color    = "var(--success)";
      if (status) { status.textContent = "Cerrado"; status.style.color = "var(--success)"; }
    }

    const fechaTxt = data.fecha_actualizada
      ? `Fecha de último mantenimiento actualizada: ${data.fecha_actualizada}.`
      : "";
    setStatus(`✓ Ticket #${_ckCtx.ticket_id} cerrado${state.modoP ? " [PRUEBA]" : ""}`, "success");
    mostrarToast(`✓ Mantenimiento de ${_ckCtx.nombre} completado. ${fechaTxt}`);

  } catch(e) {
    alert("Error al completar: " + e.message);
  } finally {
    $("btnSubmitChecklist").disabled = false;
    $("btnSubmitChecklist").textContent = "Confirmar y cerrar ticket";
  }
});

// Cerrar modal checklist clicando backdrop
$("modalChecklist").addEventListener("click", e => {
  if (e.target === $("modalChecklist")) hide("modalChecklist");
});

// Abrir editor desde el modal de checklist
$("btnEditChecklist").addEventListener("click", () => {
  hide("modalChecklist");
  abrirEditorChecklist();
});

// ══════════════════════════════════════════════════════════════════
// EDITOR DE CHECKLIST
// ══════════════════════════════════════════════════════════════════

let _editItems = [];   // copia de trabajo mientras se edita
let _dragSrc   = null; // elemento que se está arrastrando

async function abrirEditorChecklist() {
  // Cargar checklist actual desde la API
  try {
    const res = await fetch("/api/checklist");
    _editItems = await res.json();
  } catch(e) {
    alert("Error cargando checklist: " + e.message); return;
  }
  renderEditorItems();
  hide("addItemForm");
  show("modalEditChecklist");
}

function renderEditorItems() {
  const body = $("editChecklistBody");
  body.innerHTML = "";

  // Datalist de categorías existentes (para autocompletar)
  let dlId = "catList";
  let dl   = document.getElementById(dlId);
  if (!dl) { dl = document.createElement("datalist"); dl.id = dlId; document.body.appendChild(dl); }
  const cats = [...new Set(_editItems.map(i => i.categoria))];
  dl.innerHTML = cats.map(c => `<option value="${esc(c)}">`).join("");

  _editItems.forEach((item, idx) => {
    const row = document.createElement("div");
    row.className   = "edit-item-row";
    row.dataset.idx = idx;
    row.draggable   = true;

    row.innerHTML = `
      <span class="drag-handle" title="Arrastrar para reordenar">⠿</span>
      <input class="edit-item-cat"   type="text" list="catList"
             value="${esc(item.categoria)}" placeholder="Categoría"/>
      <input class="edit-item-texto" type="text"
             value="${esc(item.texto)}" placeholder="Descripción del ítem"/>
      <button class="btn-del-item" title="Eliminar ítem">✕</button>`;

    // Drag & drop nativo
    row.addEventListener("dragstart", e => {
      _dragSrc = row;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      body.querySelectorAll(".edit-item-row").forEach(r => r.classList.remove("drag-over"));
    });
    row.addEventListener("dragover", e => {
      e.preventDefault();
      if (_dragSrc && _dragSrc !== row) row.classList.add("drag-over");
    });
    row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
    row.addEventListener("drop", e => {
      e.preventDefault();
      if (!_dragSrc || _dragSrc === row) return;
      const fromIdx = parseInt(_dragSrc.dataset.idx);
      const toIdx   = parseInt(row.dataset.idx);
      // Reordenar en _editItems
      const [moved] = _editItems.splice(fromIdx, 1);
      _editItems.splice(toIdx, 0, moved);
      renderEditorItems();
    });

    // Cambios en línea se reflejan en _editItems
    row.querySelector(".edit-item-cat").addEventListener("input", e => {
      _editItems[idx].categoria = e.target.value;
      actualizarContadorEditor();
    });
    row.querySelector(".edit-item-texto").addEventListener("input", e => {
      _editItems[idx].texto = e.target.value;
      actualizarContadorEditor();
    });

    // Eliminar
    row.querySelector(".btn-del-item").addEventListener("click", () => {
      _editItems.splice(idx, 1);
      renderEditorItems();
    });

    body.appendChild(row);
  });

  actualizarContadorEditor();
}

function actualizarContadorEditor() {
  const cats  = new Set(_editItems.map(i => i.categoria).filter(Boolean));
  $("editChecklistCount").textContent =
    `${_editItems.length} ítems · ${cats.size} categorías`;
}

// ── Agregar nuevo ítem ────────────────────────────────────────────
$("btnAddItem").addEventListener("click", () => {
  show("addItemForm");
  $("newItemCategoria").focus();
  // Pre-rellenar con la última categoría usada
  if (_editItems.length > 0) {
    $("newItemCategoria").value = _editItems[_editItems.length - 1].categoria;
  }
});
$("btnCancelAddItem").addEventListener("click", () => {
  hide("addItemForm");
  $("newItemCategoria").value = "";
  $("newItemTexto").value = "";
});
$("btnConfirmAddItem").addEventListener("click", () => {
  const cat   = $("newItemCategoria").value.trim();
  const texto = $("newItemTexto").value.trim();
  if (!cat)   { $("newItemCategoria").focus(); return; }
  if (!texto) { $("newItemTexto").focus(); return; }

  const newId = `c${String(Date.now()).slice(-6)}`;
  _editItems.push({ id: newId, categoria: cat, texto });
  renderEditorItems();
  // Mantener form abierto para agregar más
  $("newItemTexto").value = "";
  $("newItemTexto").focus();
  // Scroll al final
  const body = $("editChecklistBody");
  body.scrollTop = body.scrollHeight;
});
// Confirmar con Enter en el campo texto
$("newItemTexto").addEventListener("keydown", e => {
  if (e.key === "Enter") $("btnConfirmAddItem").click();
});

// ── Restaurar predeterminado ──────────────────────────────────────
$("btnResetChecklist").addEventListener("click", async () => {
  if (!confirm("¿Restaurar el checklist al predeterminado? Se perderán todos los cambios personalizados.")) return;
  try {
    const res  = await fetch("/api/checklist/reset", { method: "POST" });
    const data = await res.json();
    _editItems = data.items;
    _ckItems   = [];  // forzar recarga en el modal de mantenimiento
    renderEditorItems();
    mostrarToast("Checklist restaurado al predeterminado");
  } catch(e) { alert("Error: " + e.message); }
});

// ── Guardar checklist personalizado ──────────────────────────────
$("btnSaveChecklist").addEventListener("click", async () => {
  // Validar que no haya items sin texto o categoría
  const invalidos = _editItems.filter(i => !i.texto.trim() || !i.categoria.trim());
  if (invalidos.length > 0) {
    alert(`Hay ${invalidos.length} ítem(s) con texto o categoría vacíos. Complétalos o elimínalos.`);
    return;
  }
  if (_editItems.length === 0) {
    alert("El checklist no puede estar vacío."); return;
  }

  $("btnSaveChecklist").disabled = true;
  $("btnSaveChecklist").innerHTML = `<span class="spinner"></span>Guardando...`;

  // Sincronizar desde los inputs (por si hubo cambios sin blur)
  $("editChecklistBody").querySelectorAll(".edit-item-row").forEach((row, i) => {
    if (_editItems[i]) {
      _editItems[i].categoria = row.querySelector(".edit-item-cat").value.trim();
      _editItems[i].texto     = row.querySelector(".edit-item-texto").value.trim();
    }
  });

  try {
    const res = await fetch("/api/checklist", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(_editItems),
    });
    if (!res.ok) { const e = await safeJson(res); throw new Error(e.detail); }
    _ckItems = [];  // forzar recarga en el modal de mantenimiento
    hide("modalEditChecklist");
    mostrarToast(`✓ Checklist guardado — ${_editItems.length} ítems`);
  } catch(e) {
    alert("Error al guardar: " + e.message);
  } finally {
    $("btnSaveChecklist").disabled = false;
    $("btnSaveChecklist").textContent = "Guardar checklist";
  }
});

// ── Cerrar modal editor ───────────────────────────────────────────
$("btnCloseEditChecklist").addEventListener("click",  () => hide("modalEditChecklist"));
$("btnCancelEditChecklist").addEventListener("click", () => hide("modalEditChecklist"));
$("modalEditChecklist").addEventListener("click", e => {
  if (e.target === $("modalEditChecklist")) hide("modalEditChecklist");
});

// ── Toast de éxito ────────────────────────────────────────────────
function mostrarToast(msg) {
  let toast = document.getElementById("toastMsg");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toastMsg";
    toast.style.cssText = `
      position:fixed; bottom:40px; left:50%; transform:translateX(-50%);
      background:var(--surf2); border:1px solid var(--success); border-radius:8px;
      color:var(--success); font-size:13px; padding:12px 20px;
      box-shadow:0 8px 24px rgba(0,0,0,.4); z-index:200;
      max-width:90vw; text-align:center; line-height:1.5;
      transition:opacity .4s;
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = "1";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toast.style.opacity = "0"; }, 4000);
}
