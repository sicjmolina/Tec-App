"use strict";

// ── Estado global ─────────────────────────────────────────────────
const state = {
  modoP: false,
  equipos: [],       // candidatos actuales con fechas asignadas
  cargado: false,
  cuota: 0,
  /** Cuántos equipos marcar para confirmar: cuota − tickets ya creados este mes (null si cuota=0). */
  cuotaMarcar: null,
  reserva: [],       // equipos elegibles no incluidos en la cuota inicial (mismo criterio GLPI)
  inventario: [],
  inventarioFiltrado: [],
  inventarioSel: null,
  inventarioUsuarios: [],
};

// ── Fechas hábiles (alineado con core/dates.py) ─────────────────
function fmtLocalYMD(d) {
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  return `${y}-${mo}-${da}`;
}

function diasHabilesJs(y, m) {
  const out = [];
  const last = new Date(y, m, 0).getDate();
  for (let d = 1; d <= last; d++) {
    const dt = new Date(y, m - 1, d);
    const wd = dt.getDay();
    if (wd >= 1 && wd <= 5) out.push(dt);
  }
  return out;
}

function asignarFechasHabilesJs(equipos) {
  const hoy = new Date();
  const y = hoy.getFullYear();
  const m = hoy.getMonth() + 1;
  let dias = diasHabilesJs(y, m);
  const hoyStr = fmtLocalYMD(hoy);
  dias = dias.filter(d => fmtLocalYMD(d) >= hoyStr);
  if (dias.length === 0) dias = diasHabilesJs(y, m);
  const total = equipos.length;
  if (total === 0) return [];
  const intervalo = Math.max(1, Math.floor(dias.length / total));
  return equipos.map((eq, i) => {
    const idx = Math.min(i * intervalo + Math.floor(intervalo / 2), dias.length - 1);
    return { ...eq, fecha_limite: fmtLocalYMD(dias[idx]) };
  });
}

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

function fmtSyncLabel(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
  } catch (_) {
    return "";
  }
}

function updateLastGlpiSync(iso) {
  const el = $("lastGlpiSync");
  if (!el) return;
  const t = fmtSyncLabel(iso);
  el.textContent = t ? `GLPI ${t}` : "";
  el.title = iso ? `Última sincronización GLPI:\n${iso}` : "Sin lectura GLPI registrada aún (modo real)";
}

async function refreshEstadoSync() {
  try {
    const r = await fetch("/api/estado");
    if (!r.ok) return;
    const d = await r.json();
    updateLastGlpiSync(d.last_glpi_sync_at);
  } catch (_) {}
}

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

function initReporteMesDefault() {
  const el = $("inpReporteMes");
  if (!el || el.value) return;
  const d = new Date();
  el.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

initReporteMesDefault();

$("btnReporteExcel").addEventListener("click", () => {
  const el = $("inpReporteMes");
  const v = el && el.value;
  if (!v || !/^\d{4}-\d{2}$/.test(v)) {
    alert("Elige un mes válido para el informe Excel.");
    return;
  }
  const [ya, mo] = v.split("-").map(Number);
  if (mo < 1 || mo > 12) {
    alert("Mes no válido.");
    return;
  }
  const url = `/api/reporte/mantenimiento-excel?anio=${ya}&mes=${mo}&modo_prueba=${state.modoP}`;
  window.location.href = url;
});

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
  if (data.last_glpi_sync_at) updateLastGlpiSync(data.last_glpi_sync_at);
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

// ── Mantenimiento: reserva / cuota UI ─────────────────────────────
function mantIdsEnLista() {
  return new Set(state.equipos.map(r => String(r.getData().id)));
}

function refreshMantAddSelect(sel) {
  if (!sel) return;
  const enLista = mantIdsEnLista();
  const keep = sel.value;
  sel.innerHTML = `<option value="">— Añadir otro equipo (reserva) —</option>`;
  for (const eq of state.reserva || []) {
    if (enLista.has(String(eq.id))) continue;
    const o = document.createElement("option");
    o.value = String(eq.id);
    o.textContent = `${eq.nombre} · últ. mant. ${eq.ultima_fecha || "—"}`;
    sel.appendChild(o);
  }
  if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
}

function renumberEquipoRows() {
  state.equipos.forEach((r, j) => {
    const tag = r.el.querySelector(".equipo-idx");
    if (tag) tag.textContent = `EQUIPO ${String(j + 1).padStart(2, "0")}`;
  });
}

function cuotaRequeridaMarcar() {
  const cuota = state.cuota || 0;
  if (cuota <= 0) return null;
  if (state.modoP) return cuota;
  return state.cuotaMarcar != null ? state.cuotaMarcar : cuota;
}

function updateMarcadosCuotaStat() {
  const cuota = state.cuota || 0;
  const n = state.equipos.filter(r => r.getData().incluido).length;
  const numPend = $("cstatPendientes")?.querySelector(".cuota-stat-num");
  if (!numPend) return;
  numPend.textContent = String(n);
  if (cuota <= 0) {
    numPend.style.color = "var(--muted)";
    return;
  }
  const req = cuotaRequeridaMarcar();
  numPend.style.color = n === req ? "var(--success)" : "var(--warning)";
}

function updatePendientesUi() {
  updateMarcadosCuotaStat();
  const sec = $("mantSecPendTitle");
  if (sec) {
    const lista = state.equipos.length;
    const n = state.equipos.filter(r => r.getData().incluido).length;
    const c = state.cuota;
    const req = cuotaRequeridaMarcar();
    if (c > 0 && req != null) {
      const yaCon = c - req;
      sec.textContent =
        `PENDIENTES DE CREAR (${lista} en lista · ${n}/${req} marcados para completar cuota · ${yaCon} ya con ticket)`;
    } else {
      sec.textContent = `PENDIENTES DE CREAR (${lista} en lista)`;
    }
  }
  refreshMantAddSelect($("mantAddSelect"));
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

  const list = $("equiposList");
  list.innerHTML = "";
  state.equipos = [];
  state.cuota = data.cuota;
  state.reserva = data.reserva || [];
  {
    const c = data.cuota || 0;
    const conT = (data.tickets_mes || []).length;
    state.cuotaMarcar = c > 0 ? Math.max(0, c - conT) : null;
  }

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
    $("btnConfirmar").title = "";
    return;
  }

  const secPend = document.createElement("p");
  secPend.className = "sec-title";
  secPend.id = "mantSecPendTitle";
  list.appendChild(secPend);

  const pendOuter = document.createElement("div");
  pendOuter.className = "mant-pend-outer";

  if (state.reserva.length > 0) {
    const bar = document.createElement("div");
    bar.className = "mant-add-bar";
    const lab = document.createElement("span");
    lab.className = "mant-add-lbl";
    lab.textContent = "Añadir equipo desde la reserva (misma elegibilidad que la cuota):";
    const sel = document.createElement("select");
    sel.id = "mantAddSelect";
    sel.className = "mant-add-select";
    const btnA = document.createElement("button");
    btnA.type = "button";
    btnA.className = "btn btn-primary btn-sm";
    btnA.id = "mantAddBtn";
    btnA.textContent = "Añadir a la lista";
    btnA.addEventListener("click", () => onMantAddEquipo());
    bar.appendChild(lab);
    bar.appendChild(sel);
    bar.appendChild(btnA);
    pendOuter.appendChild(bar);
  }

  const pendWrap = document.createElement("div");
  pendWrap.id = "mantPendRows";
  pendOuter.appendChild(pendWrap);
  list.appendChild(pendOuter);

  for (let i = 0; i < data.candidatos.length; i++) {
    const eq  = data.candidatos[i];
    const row = buildEquipoRow(i, eq, updatePendientesUi);
    pendWrap.appendChild(row.el);
    state.equipos.push(row);
  }

  refreshMantAddSelect($("mantAddSelect"));
  updatePendientesUi();

  const sinPendienteCuota = state.cuota > 0 && state.cuotaMarcar === 0;
  $("btnConfirmar").disabled = sinPendienteCuota;
  $("btnConfirmar").title = sinPendienteCuota
    ? "La cuota del mes ya está cubierta por los tickets actuales."
    : "";
  $("btnConfirmar").className = "btn btn-success";
}

// ── Equipo row editable ───────────────────────────────────────────
function buildEquipoRow(idx, eq, onUiUpdate) {
  const el = document.createElement("div");
  el.className = "equipo-row";
  el.dataset.idx = idx;

  const sinHistorial = !eq.ultima_fecha || eq.ultima_fecha.startsWith("1990");
  if (sinHistorial) el.classList.add("sin-historial");

  el.innerHTML = `
    <div class="equipo-row-actions">
      <input type="checkbox" checked title="Incluir en la creación (debe coincidir con los equipos faltantes de la cuota)"/>
      <button type="button" class="btn btn-ghost btn-sm equipo-quitar">Quitar</button>
    </div>
    <div class="equipo-info">
      <span class="equipo-idx">EQUIPO ${String(idx+1).padStart(2,"0")}</span>
      <div class="equipo-nombre">
        ${esc(eq.nombre)}
        ${sinHistorial ? `<span class="badge-sin-registro" title="Sin mantenimiento registrado en GLPI">SIN REGISTRO</span>` : ""}
      </div>
      ${(eq.usuario_asignado || "").trim()
        ? `<div class="equipo-usuario-asignado" title="Usuario asignado al equipo en GLPI">👤 ${esc((eq.usuario_asignado || "").trim())}</div>`
        : `<div class="equipo-usuario-asignado sin-usuario">Sin usuario asignado en GLPI</div>`}
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
    if (onUiUpdate) onUiUpdate();
  });

  // Validación visual de fecha
  const inpFecha = el.querySelector(".inp-fecha");
  inpFecha.addEventListener("change", () => {
    inpFecha.style.borderColor = inpFecha.value ? "" : "var(--danger)";
  });

  const ctl = {
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

  el.querySelector(".equipo-quitar").addEventListener("click", () => {
    const i = state.equipos.indexOf(ctl);
    if (i >= 0) state.equipos.splice(i, 1);
    el.remove();
    renumberEquipoRows();
    refreshMantAddSelect($("mantAddSelect"));
    updatePendientesUi();
  });

  return ctl;
}

function onMantAddEquipo() {
  const sel = $("mantAddSelect");
  if (!sel || !sel.value) {
    alert("Elige un equipo en el desplegable.");
    return;
  }
  const id = sel.value;
  const eq = state.reserva.find(e => String(e.id) === id);
  if (!eq) return;
  const copy = { ...eq };
  const withFecha = asignarFechasHabilesJs([copy])[0];
  const pendWrap = $("mantPendRows");
  if (!pendWrap) return;
  const rowCtl = buildEquipoRow(state.equipos.length, withFecha, updatePendientesUi);
  state.equipos.push(rowCtl);
  pendWrap.appendChild(rowCtl.el);
  sel.value = "";
  refreshMantAddSelect(sel);
  renumberEquipoRows();
  updatePendientesUi();
}

// ── Confirmar ─────────────────────────────────────────────────────
$("btnConfirmar").addEventListener("click", () => {
  if (!state.cargado) return;

  const cuota = state.cuota || 0;
  const nIncl = state.equipos.filter(r => r.getData().incluido).length;
  const req = cuotaRequeridaMarcar();
  if (cuota > 0 && req != null) {
    if (req === 0) {
      alert("La cuota del mes ya está cubierta. No hace falta confirmar más equipos.");
      return;
    }
    if (nIncl !== req) {
      const conT = cuota - req;
      alert(
        `Para completar la cuota de ${cuota} equipo(s) debes marcar exactamente ${req} (ya hay ${conT} con ticket este mes).\n` +
        `Ahora hay ${nIncl} marcado(s). Ajusta la lista o las casillas.`
      );
      return;
    }
  }

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
    cuota_mes: state.cuota || 0,
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
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { refreshEstadoSync(); });
} else {
  refreshEstadoSync();
}

$("btnInventario").addEventListener("click", async () => {
  await cargarInventario();
  show("modalInventario");
});

$("btnCloseInventario").addEventListener("click", () => hide("modalInventario"));
$("btnInvRefresh").addEventListener("click", async () => { await cargarInventario(); });
$("btnInvCsvActivos").addEventListener("click", () => {
  window.location.href = `/api/inventario/activos.csv?modo_prueba=${state.modoP}`;
});
$("btnInvCsv").addEventListener("click", () => {
  let url = `/api/inventario/historial.csv`;
  if (state.inventarioSel?.asset_id) {
    url += `?asset_id=${encodeURIComponent(state.inventarioSel.asset_id)}`;
  }
  window.location.href = url;
});
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
    await refreshEstadoSync();
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
  const syncEl = $("lastGlpiSync");
  const syncShort = (syncEl && syncEl.textContent) ? ` · ${syncEl.textContent}` : "";
  $("invResumen").textContent = `Total: ${total} · Bajas: ${bajas} · Activos: ${total - bajas}${syncShort}`;

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

// ══════════════════════════════════════════════════════════════════
// RENOVACIÓN DE EQUIPOS
// ══════════════════════════════════════════════════════════════════
const renState = {
  raw: null,
  excludedActivos: new Set(),
  excludedCandidatos: new Set(),
  manualReplacementByActivo: {}, // { activoId: inactivoId }
  /** IDs de activos incluidos a mano en la lista de “débiles” (Set de string) */
  manualDebilesIds: new Set(),
  computed: null,
  /** { [activoId]: true|false }; undefined = aplicar (marcado por defecto) */
  aplicarEnGlpi: {},
};

$("btnRenovacion").addEventListener("click", () => {
  show("modalRenovacion");
});
$("btnCloseRenovacion").addEventListener("click", () => hide("modalRenovacion"));
$("modalRenovacion").addEventListener("click", e => {
  if (e.target === $("modalRenovacion")) hide("modalRenovacion");
});

$("btnRenAnalizar").addEventListener("click", async () => {
  const btn = $("btnRenAnalizar");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>Analizando...`;
  $("renStatus").textContent = "";
  hide("btnRenExcel");
  hide("btnRenAplicar");
  hide("renResponsable");
  hide("renAplicarHint");
  hide("btnRenAplicarMarcar");
  hide("btnRenAplicarNinguno");

  try {
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), 45000);
    const res = await fetch(`/api/renovacion?modo_prueba=${state.modoP}`, { signal: ctl.signal });
    clearTimeout(to);
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Error HTTP ${res.status}`);
    }
    const data = await res.json();
    renState.raw = data;
    renState.excludedActivos.clear();
    renState.excludedCandidatos.clear();
    renState.manualReplacementByActivo = {};
    renState.manualDebilesIds.clear();
    renState.aplicarEnGlpi = {};
    recomputeRenovacion();
    renderRenovacion();
    show("btnRenReset");
  } catch (e) {
    const msg = e.name === "AbortError"
      ? "Tiempo de análisis agotado (45s). Reintenta o reduce carga."
      : e.message;
    $("renStatus").textContent = `✗ ${msg}`;
    $("renStatus").style.color = "var(--danger)";
  } finally {
    btn.disabled = false;
    btn.innerHTML = "▶ Analizar equipos";
  }
});

$("btnRenExcel").addEventListener("click", async () => {
  const data = renState.computed;
  if (!data) return;

  const btn = $("btnRenExcel");
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = "Generando...";
  try {
    const res = await fetch("/api/renovacion/excel-custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Error HTTP ${res.status}`);
    }

    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") || "";
    const m = /filename=([^;]+)/i.exec(cd);
    const filename = (m?.[1] || `renovacion_personalizada_${new Date().toISOString().slice(0,10)}.xlsx`).replace(/"/g, "");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("No se pudo generar el Excel:\n" + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
});

function renSyncAplicarChoices() {
  const data = renState.computed;
  if (!data?.pares) return;
  const keep = new Set(
    data.pares.filter(p => p.reemplazo).map(p => String(p.activo.id))
  );
  for (const k of Object.keys(renState.aplicarEnGlpi)) {
    if (!keep.has(k)) delete renState.aplicarEnGlpi[k];
  }
}

function renSelectedParesForGlpi() {
  const data = renState.computed;
  if (!data?.pares) return [];
  return data.pares.filter(
    p => p.reemplazo && renState.aplicarEnGlpi[String(p.activo.id)] !== false
  );
}

function renUpdateAplicarHint() {
  const el = $("renAplicarHint");
  if (!el) return;
  const data = renState.computed;
  const total = (data?.pares || []).filter(p => p.reemplazo).length;
  const n = renSelectedParesForGlpi().length;
  if (total > 0) {
    el.textContent = `${n} de ${total} para aplicar en GLPI`;
    show("renAplicarHint");
  } else {
    hide("renAplicarHint");
  }
}

function renPayloadConfirmar() {
  const data = renState.computed;
  if (!data?.pares) return null;
  const pares = renSelectedParesForGlpi();
  if (!pares.length) return null;
  return {
    modo_prueba: state.modoP,
    responsable: ($("renResponsable")?.value || "").trim(),
    estado_reemplazo: "Activo",
    estado_debil: "Inactivo",
    pares,
  };
}

function renSetAllAplicarMarcado(val) {
  const data = renState.computed;
  if (!data?.pares) return;
  for (const p of data.pares) {
    if (p.reemplazo) renState.aplicarEnGlpi[String(p.activo.id)] = val;
  }
  renUpdateAplicarHint();
  renderRenovacion();
}

$("btnRenAplicarMarcar")?.addEventListener("click", () => renSetAllAplicarMarcado(true));
$("btnRenAplicarNinguno")?.addEventListener("click", () => renSetAllAplicarMarcado(false));

$("btnRenAplicar").addEventListener("click", () => {
  const payload = renPayloadConfirmar();
  if (!payload) {
    alert("Marca al menos un reemplazo con «Aplicar este reemplazo en GLPI» o pulsa «Marcar todos».");
    return;
  }
  const n = payload.pares.length;
  const modoTxt = state.modoP
    ? "Modo prueba: no se escribirá nada en GLPI (solo simulación)."
    : "Se modificará GLPI: en cada par se asignará el usuario del equipo débil al de reemplazo (estado Activo) y el equipo débil quedará sin usuario y en estado Inactivo.";
  openConfirm(
    state.modoP ? "Simular renovación en GLPI" : "Aplicar renovación en GLPI",
    `${modoTxt}\n\n¿Continuar con ${n} reemplazo(s)?`,
    async () => {
      const btn = $("btnRenAplicar");
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = "Aplicando...";
      $("renStatus").textContent = "";
      try {
        const res = await fetch("/api/renovacion/confirmar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const body = await safeJson(res);
        if (!res.ok) {
          throw new Error(body?.detail || `Error HTTP ${res.status}`);
        }
        const ok = body.ok;
        const aplicados = body.aplicados || [];
        const errores = body.errores || [];
        let msg = ok
          ? `✓ ${aplicados.length} renovación(es) ${state.modoP ? "simulada(s)" : "aplicada(s)"}.`
          : `Hecho con incidencias: ${aplicados.length} ok, ${errores.length} error(es).`;
        if (errores.length) msg += "\n\n" + errores.join("\n");
        $("renStatus").textContent = msg.split("\n")[0];
        $("renStatus").style.color = ok ? "var(--success)" : "var(--warning)";
        alert(msg);
      } catch (e) {
        $("renStatus").textContent = `✗ ${e.message}`;
        $("renStatus").style.color = "var(--danger)";
        alert("Error al aplicar renovación:\n" + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = prev;
      }
    }
  );
});

$("btnRenReset").addEventListener("click", () => {
  renState.excludedActivos.clear();
  renState.excludedCandidatos.clear();
  renState.manualReplacementByActivo = {};
  renState.aplicarEnGlpi = {};
  recomputeRenovacion();
  renderRenovacion();
});

$("btnRenDiag").addEventListener("click", async () => {
  const btn = $("btnRenDiag");
  const panel = $("renDiagPanel");
  const pre   = $("renDiagContent");
  btn.disabled = true;
  btn.textContent = "Cargando...";
  hide("renDiagPanel");
  try {
    const res = await fetch("/api/renovacion/diagnostico");
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Error HTTP ${res.status}`);
    }
    const data = await res.json();
    pre.textContent = JSON.stringify(data, null, 2);
    show("renDiagPanel");
  } catch (e) {
    pre.textContent = `Error: ${e.message}`;
    show("renDiagPanel");
  } finally {
    btn.disabled = false;
    btn.textContent = "🔍 Diagnóstico GLPI";
  }
});
$("btnRenDiagClose").addEventListener("click", () => hide("renDiagPanel"));

/** Misma lógica que el backend (`renovation._estado_cat`) para filtrar activos. */
function renEstadoCat(estado) {
  const s = String(estado ?? "").trim().toLowerCase();
  if (s === "1") return "activo";
  if (s === "2") return "inactivo";
  if (s.includes("inactivo") || s.includes("stock") || s.includes("reserva") || s.includes("almacen") || s.includes("almacén")) return "inactivo";
  if (s.includes("activo") || s.includes("en uso") || s.includes("produccion") || s.includes("producción")) return "activo";
  if (s.includes("baja") || s.includes("retir") || s.includes("obsole")) return "baja";
  return "otro";
}

function recomputeRenovacion() {
  const data = renState.raw;
  if (!data) {
    renState.computed = null;
    return;
  }

  const rawDebiles = (data.debiles_items || [])
    .filter(d => !renState.excludedActivos.has(String(d.id)));
  const baseIds = new Set(rawDebiles.map(d => String(d.id)));
  for (const sid of [...renState.manualDebilesIds]) {
    if (baseIds.has(sid)) renState.manualDebilesIds.delete(sid);
  }

  const todos = data.todos || [];
  const manualExtras = [];
  for (const sid of [...renState.manualDebilesIds]) {
    const eq = todos.find(t => String(t.id) === sid);
    if (!eq || renEstadoCat(eq.estado) !== "activo") {
      renState.manualDebilesIds.delete(sid);
      continue;
    }
    if (renState.excludedActivos.has(sid)) continue;
    manualExtras.push(eq);
  }

  const debiles = [...rawDebiles, ...manualExtras].sort((a, b) => (a.score || 0) - (b.score || 0));
  const inactivos = (data.inactivos_items || [])
    .filter(c => !renState.excludedCandidatos.has(String(c.id)))
    .sort((a, b) => (b.score || 0) - (a.score || 0));

  // Limpiar selecciones manuales inválidas por descartes/ausencia
  for (const [aid, iid] of Object.entries(renState.manualReplacementByActivo)) {
    const okActivo = debiles.some(d => String(d.id) === String(aid));
    const okInactivo = inactivos.some(i => String(i.id) === String(iid));
    if (!okActivo || !okInactivo) delete renState.manualReplacementByActivo[aid];
  }

  const manualUsed = new Set(Object.values(renState.manualReplacementByActivo).map(String));
  const pares = [];
  const usadosAuto = new Set();
  for (const d of debiles) {
    const manualId = renState.manualReplacementByActivo[String(d.id)];
    const manual = inactivos.find(c => String(c.id) === String(manualId)) || null;
    const mejorAuto = inactivos.find(c =>
      !manualUsed.has(String(c.id)) &&
      !usadosAuto.has(String(c.id)) &&
      (c.score || 0) > (d.score || 0)
    ) || null;
    const mejor = manual || mejorAuto;
    pares.push({
      activo: d,
      reemplazo: mejor,
      mejora_ram: mejor ? Math.floor(((mejor.ram_mb || 0) - (d.ram_mb || 0)) / 1024) : 0,
      mejora_disco: mejor ? ((mejor.disco_gb || 0) - (d.disco_gb || 0)) : 0,
      mejora_ssd: mejor ? ((mejor.tipo_disco || "").toUpperCase().includes("SSD") && !(d.tipo_disco || "").toUpperCase().includes("SSD")) : false,
      ganancia_score: mejor ? ((mejor.score || 0) - (d.score || 0)) : 0,
    });
    if (!manual && mejorAuto) usadosAuto.add(String(mejorAuto.id));
  }

  renState.computed = {
    total_activos: data.total_activos || 0,
    total_inactivos: data.total_inactivos || 0,
    debiles_base: data.debiles || 0,
    candidatos_base: data.candidatos || 0,
    debiles: debiles.length,
    candidatos: inactivos.length,
    inactivos_disponibles: inactivos,
    pares,
    todos: data.todos || [],
  };
}

function buildManualAddBar(data) {
  const bar = document.createElement("div");
  bar.className = "ren-manual-add";

  const hint = document.createElement("p");
  hint.className = "ren-manual-add-hint";
  hint.textContent = "¿Falta algún activo? Añádelo aquí para buscarle reemplazo como al resto de equipos débiles.";
  bar.appendChild(hint);

  const row = document.createElement("div");
  row.className = "ren-manual-add-row";

  const sel = document.createElement("select");
  sel.className = "ren-select ren-manual-add-select";

  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "— Seleccionar equipo activo —";
  sel.appendChild(empty);

  const shownIds = new Set((data.pares || []).map(p => String(p.activo.id)));
  const todos = renState.raw?.todos || [];
  const candidates = todos
    .filter(t => renEstadoCat(t.estado) === "activo" && !shownIds.has(String(t.id)))
    .sort((a, b) => String(a.nombre || "").localeCompare(String(b.nombre || ""), "es", { sensitivity: "base" }));

  for (const t of candidates) {
    const o = document.createElement("option");
    o.value = String(t.id);
    const sc = t.score ?? 0;
    o.textContent = `${t.nombre || "(sin nombre)"} · Score ${sc}`;
    sel.appendChild(o);
  }

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn btn-primary btn-sm";
  btn.textContent = "Añadir a la lista";
  btn.addEventListener("click", () => {
    const v = sel.value;
    if (!v) return;
    renState.manualDebilesIds.add(v);
    recomputeRenovacion();
    renderRenovacion();
  });

  row.appendChild(sel);
  row.appendChild(btn);
  bar.appendChild(row);
  return bar;
}

function renderRenovacion() {
  const data = renState.computed;
  if (!data) return;

  renSyncAplicarChoices();

  // Stats
  const s = $("renStats");
  s.classList.remove("hidden");
  $("renStatActivos").querySelector(".ren-stat-num").textContent    = data.total_activos;
  $("renStatDebiles").querySelector(".ren-stat-num").textContent    = data.debiles;
  $("renStatInactivos").querySelector(".ren-stat-num").textContent  = data.total_inactivos;
  $("renStatCandidatos").querySelector(".ren-stat-num").textContent = data.candidatos;

  const wrap = $("renTableWrap");
  wrap.innerHTML = "";

  wrap.appendChild(buildManualAddBar(data));

  const exclInfo = document.createElement("p");
  exclInfo.className = "muted";
  exclInfo.style.marginBottom = "10px";
  exclInfo.textContent = `Descartes aplicados: ${renState.excludedActivos.size} activos · ${renState.excludedCandidatos.size} inactivos`;
  wrap.appendChild(exclInfo);

  if (!data.pares || data.pares.length === 0) {
    const msg = document.createElement("p");
    msg.className = "muted";
    msg.style.cssText = "text-align:center;padding:24px 0 8px";
    msg.textContent = "No hay equipos en la lista de débiles (automáticos descartados o ninguno detectado). Puedes añadir activos arriba.";
    wrap.appendChild(msg);
    show("btnRenExcel");
    hide("btnRenAplicar");
    hide("renResponsable");
    hide("renAplicarHint");
    hide("btnRenAplicarMarcar");
    hide("btnRenAplicarNinguno");
    renUpdateAplicarHint();
    $("renStatus").textContent = `✓ ${data.debiles} en lista débil · 0 reemplazos en pantalla${state.modoP ? " [PRUEBA]" : ""}`;
    $("renStatus").style.color = "var(--success)";
    return;
  }

  const conReemplazo   = data.pares.filter(p => p.reemplazo);
  const sinReemplazo   = data.pares.filter(p => !p.reemplazo);

  if (conReemplazo.length) {
    show("btnRenAplicar");
    show("renResponsable");
    show("btnRenAplicarMarcar");
    show("btnRenAplicarNinguno");
  } else {
    hide("btnRenAplicar");
    hide("renResponsable");
    hide("btnRenAplicarMarcar");
    hide("btnRenAplicarNinguno");
    hide("renAplicarHint");
  }

  if (conReemplazo.length) {
    const t1 = document.createElement("div");
    t1.className = "ren-section-title";
    t1.textContent = `REEMPLAZOS RECOMENDADOS (${conReemplazo.length})`;
    wrap.appendChild(t1);
    for (const p of conReemplazo) wrap.appendChild(buildPairCard(p));
  }

  if (sinReemplazo.length) {
    const t2 = document.createElement("div");
    t2.className = "ren-section-title";
    t2.style.color = "var(--warning)";
    t2.textContent = `SIN REEMPLAZO DISPONIBLE (${sinReemplazo.length})`;
    wrap.appendChild(t2);
    for (const p of sinReemplazo) wrap.appendChild(buildPairCard(p));
  }

  show("btnRenExcel");
  renUpdateAplicarHint();
  $("renStatus").textContent = `✓ ${data.debiles} equipos débiles (de ${data.debiles_base}) · ${conReemplazo.length} reemplazos disponibles${state.modoP ? " [PRUEBA]" : ""}`;
  $("renStatus").style.color = "var(--success)";
}

function buildExcludeToggle(label, checked, onChange) {
  const wrap = document.createElement("label");
  wrap.className = "ren-exclude";
  const chk = document.createElement("input");
  chk.type = "checkbox";
  chk.checked = checked;
  chk.addEventListener("change", onChange);
  const txt = document.createElement("span");
  txt.textContent = label;
  wrap.appendChild(chk);
  wrap.appendChild(txt);
  return wrap;
}

function buildPairCard(p) {
  const d = p.activo;
  const r = p.reemplazo;
  const card = document.createElement("div");
  card.className = `ren-pair-card${r ? "" : " sin-candidato"}`;

  const mejoras = [];
  if (p.mejora_ram > 0)   mejoras.push(`+${p.mejora_ram} GB RAM`);
  if (p.mejora_disco > 0) mejoras.push(`+${p.mejora_disco} GB disco`);
  if (p.mejora_ssd)       mejoras.push("HDD → SSD");

  card.innerHTML = `
    <div class="ren-side ren-side-debil">
      <div class="ren-side-nombre">${esc(d.nombre)}</div>
      <div class="ren-side-meta">
        ${d.usuario ? `Usuario: ${esc(d.usuario)}<br>` : ""}
        ${d.serial   ? `Serial: ${esc(d.serial)}<br>` : ""}
        ${d.fabricante ? `${esc(d.fabricante)} ${esc(d.modelo || "")}` : ""}
      </div>
      <div class="ren-side-meta" style="margin-top:4px">${esc(d.specs_fmt)}</div>
      <span class="ren-score-pill ren-score-debil">Score: ${d.score}/100</span>
    </div>
    <div class="ren-side-arrow">→</div>
    <div class="ren-side ren-side-candid">
      ${r ? `
        <div class="ren-side-nombre">${esc(r.nombre)}</div>
        <div class="ren-side-meta">
          ${r.serial ? `Serial: ${esc(r.serial)}<br>` : ""}
          ${r.fabricante ? `${esc(r.fabricante)} ${esc(r.modelo || "")}` : ""}
        </div>
        <div class="ren-side-meta" style="margin-top:4px">${esc(r.specs_fmt)}</div>
        <span class="ren-score-pill ren-score-candid">Score: ${r.score}/100</span>
        ${mejoras.length ? `<div class="ren-mejoras">▲ ${esc(mejoras.join(" · "))}</div>` : ""}
      ` : `
        <div class="ren-side-nombre" style="color:var(--muted)">Sin candidato disponible</div>
        <div class="ren-side-meta">No hay equipos inactivos con mejores especificaciones.</div>
      `}
    </div>`;

  const left = card.querySelector(".ren-side-debil");
  const nombreEl = left.querySelector(".ren-side-nombre");

  if (r) {
    const aid = String(d.id);
    const applyLbl = document.createElement("label");
    applyLbl.className = "ren-apply-in-card";
    const applyChk = document.createElement("input");
    applyChk.type = "checkbox";
    applyChk.checked = renState.aplicarEnGlpi[aid] !== false;
    applyChk.addEventListener("change", () => {
      renState.aplicarEnGlpi[aid] = applyChk.checked;
      renUpdateAplicarHint();
    });
    const applyTxt = document.createElement("span");
    applyTxt.textContent = "Aplicar este reemplazo en GLPI";
    applyLbl.appendChild(applyChk);
    applyLbl.appendChild(applyTxt);
    left.insertBefore(applyLbl, left.firstChild);
  }

  if (renState.manualDebilesIds.has(String(d.id))) {
    const badge = document.createElement("span");
    badge.className = "ren-manual-badge";
    badge.textContent = "Manual";
    nombreEl.appendChild(document.createTextNode(" "));
    nombreEl.appendChild(badge);
  }

  left.appendChild(
    buildExcludeToggle(
      "Descartar este equipo activo",
      renState.excludedActivos.has(String(d.id)),
      () => {
        if (renState.excludedActivos.has(String(d.id))) renState.excludedActivos.delete(String(d.id));
        else renState.excludedActivos.add(String(d.id));
        recomputeRenovacion();
        renderRenovacion();
      }
    )
  );

  if (renState.manualDebilesIds.has(String(d.id))) {
    const btnQuitar = document.createElement("button");
    btnQuitar.type = "button";
    btnQuitar.className = "btn btn-ghost btn-sm ren-manual-quitar";
    btnQuitar.textContent = "Quitar de la lista manual";
    btnQuitar.addEventListener("click", () => {
      renState.manualDebilesIds.delete(String(d.id));
      recomputeRenovacion();
      renderRenovacion();
    });
    left.appendChild(btnQuitar);
  }

  const right = card.querySelector(".ren-side-candid");
  if (r) {
    right.appendChild(
      buildExcludeToggle(
        "No usar este equipo inactivo",
        renState.excludedCandidatos.has(String(r.id)),
        () => {
          if (renState.excludedCandidatos.has(String(r.id))) renState.excludedCandidatos.delete(String(r.id));
          else renState.excludedCandidatos.add(String(r.id));
          recomputeRenovacion();
          renderRenovacion();
        }
      )
    );
  }

  // Selector manual: mostrar TODOS los inactivos disponibles.
  const pickerWrap = document.createElement("div");
  pickerWrap.className = "ren-side-meta";
  pickerWrap.style.marginTop = "8px";

  const selectId = `renSel_${String(d.id)}`;
  const label = document.createElement("label");
  label.setAttribute("for", selectId);
  label.textContent = "Elegir inactivo manualmente:";
  label.style.display = "block";
  label.style.marginBottom = "4px";
  label.style.color = "var(--accent)";
  pickerWrap.appendChild(label);

  const sel = document.createElement("select");
  sel.id = selectId;
  sel.className = "ren-select";

  const optAuto = document.createElement("option");
  optAuto.value = "";
  optAuto.textContent = "Automático (mejor candidato)";
  sel.appendChild(optAuto);

  const inactivos = renState.computed?.inactivos_disponibles || [];
  for (const i of inactivos) {
    const o = document.createElement("option");
    o.value = String(i.id);
    const better = (i.score || 0) > (d.score || 0) ? "↑" : "·";
    o.textContent = `${better} ${i.nombre} (Score ${i.score || 0})`;
    sel.appendChild(o);
  }

  const manual = renState.manualReplacementByActivo[String(d.id)] || "";
  sel.value = manual;
  sel.addEventListener("change", () => {
    const v = sel.value;
    if (!v) delete renState.manualReplacementByActivo[String(d.id)];
    else renState.manualReplacementByActivo[String(d.id)] = v;
    recomputeRenovacion();
    renderRenovacion();
  });
  pickerWrap.appendChild(sel);
  right.appendChild(pickerWrap);

  return card;
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
["modalConfig","modalConfirmar","modalResult","modalInventario","modalRenovacion"].forEach(id => {
  $(id).addEventListener("click", e => {
    if (e.target === $(id)) hide(id);
  });
});

// ── Escape cierra modales ─────────────────────────────────────────
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    ["modalConfig","modalConfirmar","modalResult","modalInventario","modalRenovacion"].forEach(hide);
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
