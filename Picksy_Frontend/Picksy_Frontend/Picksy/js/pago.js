// CAMBIO (pagos): ventana de membresía y pagos. Se llega desde el menú "Membresía" o desde el botón "Membresía" de un carrito.
//
// Picksy no vende los productos: lo único que se cobra es el uso de la página (membresía mensual, semestral o anual).
// Flujo: 1. plan  2. método de pago  3. "Continuar al pago" -> el backend crea el pago y envía el correo
//        4. "Confirmar y pagar" -> la membresía queda activa (y llega el comprobante por correo).
//
// MODO DEMOSTRACIÓN: el pago es simulado. Nunca se pide ni se envía el número de la tarjeta, solo la marca y los últimos 4 dígitos.
// Todo texto que viene del servidor se inserta con textContent (nunca como HTML).

const $ = (s) => document.querySelector(s);
const pesos = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

const TIPOS = [
  ["tarjeta_credito", "Tarjeta de crédito"],
  ["tarjeta_debito", "Tarjeta débito"],
  ["pse", "PSE (transferencia bancaria)"],
  ["nequi", "Nequi"],
];
const MARCAS = ["Visa", "Mastercard", "American Express", "Otra"];
const ESTADOS = { pendiente: "Pendiente", pagado: "Pagado", cancelado: "Cancelado", vencido: "Vencido" };

const estado = { planes: [], metodos: [], metodoId: null, plan: "anual", pago: null };

// ---------- utilidades ----------
function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos)) {
    if (k === "class") nodo.className = v;
    else if (k === "text") nodo.textContent = v;
    else nodo.setAttribute(k, v);
  }
  nodo.append(...hijos);
  return nodo;
}

function mensaje(texto, esError = false) {
  const f = $("#pagoFeedback");
  f.textContent = texto || "";
  f.style.color = esError ? "#B54E51" : "#65854C";
}

function aviso(texto) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = texto;
  t.classList.add("show");
  window.clearTimeout(aviso.timer);
  aviso.timer = window.setTimeout(() => t.classList.remove("show"), 2600);
}

function mostrar(vista) {
  for (const id of ["vistaCheckout", "vistaConfirmar", "vistaExito"]) {
    $("#" + id).hidden = id !== vista;
  }
}

function filas(dl, pares) {
  dl.replaceChildren();
  for (const [k, v, clase] of pares) {
    dl.append(el("dt", { text: k, class: clase || "" }), el("dd", { text: v, class: clase || "" }));
  }
}

function fecha(iso) {
  return new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}

async function intentar(accion, boton) {
  if (boton) boton.disabled = true;
  mensaje("");
  try {
    return await accion();
  } catch (error) {
    mensaje(error.message, true);
    return undefined;
  } finally {
    if (boton) boton.disabled = false;
  }
}

// ---------- formulario para agregar un método de pago ----------
// Nunca hay un campo para el número completo: solo los últimos 4 dígitos.
function formularioMetodo(contenedor, alGuardar) {
  contenedor.replaceChildren();
  const abrir = el("button", { type: "button", class: "button button-secondary button-mini", text: "+ Agregar método de pago" });

  const tipo = el("select", { id: "metodoTipo" }, ...TIPOS.map(([v, t]) => el("option", { value: v, text: t })));
  const marca = el("select", { id: "metodoMarca" }, ...MARCAS.map((m) => el("option", { value: m, text: m })));
  const ultimos4 = el("input", { id: "metodoUltimos4", type: "text", inputmode: "numeric", maxlength: "4", pattern: "[0-9]{4}", placeholder: "4242", autocomplete: "off" });
  const banco = el("input", { id: "metodoBanco", type: "text", maxlength: "60", placeholder: "Bancolombia" });
  const alias = el("input", { id: "metodoAlias", type: "text", maxlength: "50", placeholder: "Mi tarjeta personal", required: "" });
  const pred = el("input", { id: "metodoPred", type: "checkbox" });
  const etiquetaUltimos4 = el("label", { for: "metodoUltimos4", text: "Últimos 4 dígitos de la tarjeta" });
  const campo = (etiqueta, input, extra = "") => el("div", { class: "form-vertical " + extra }, etiqueta, input);
  const cMarca = campo(el("label", { for: "metodoMarca", text: "Marca" }), marca);
  const cUltimos = el("div", { class: "form-vertical" }, etiquetaUltimos4, ultimos4);
  const cBanco = campo(el("label", { for: "metodoBanco", text: "Banco" }), banco, "campo-oculto");
  const error = el("p", { class: "dialogo-error", role: "alert" });

  const guardar = el("button", { type: "submit", class: "button button-primary button-mini", text: "Guardar método" });
  const cancelar = el("button", { type: "button", class: "button button-secondary button-mini", text: "Cancelar" });

  const form = el("form", { class: "metodo-form form-vertical", id: "formMetodo", hidden: "", novalidate: "" },
    campo(el("label", { for: "metodoTipo", text: "Tipo" }), tipo),
    el("div", { class: "fila-2" }, cMarca, cUltimos),
    cBanco,
    campo(el("label", { for: "metodoAlias", text: "Nombre para reconocerlo" }), alias),
    el("label", { class: "codigos-confirmar" }, pred, document.createTextNode(" Usar como método predeterminado")),
    el("p", { class: "nota", text: "No pedimos el número completo de la tarjeta ni el código de seguridad (CVV)." }),
    error,
    el("div", { class: "acciones" }, guardar, cancelar));

  function ajustar() {
    const t = tipo.value;
    cMarca.classList.toggle("campo-oculto", t === "pse" || t === "nequi");
    cUltimos.classList.toggle("campo-oculto", t === "pse");
    cBanco.classList.toggle("campo-oculto", t !== "pse");
    etiquetaUltimos4.textContent = t === "nequi" ? "Últimos 4 dígitos del celular Nequi" : "Últimos 4 dígitos de la tarjeta";
  }
  tipo.addEventListener("change", ajustar);
  ajustar();

  abrir.addEventListener("click", () => { form.hidden = false; abrir.hidden = true; alias.focus(); });
  cancelar.addEventListener("click", () => { form.hidden = true; abrir.hidden = false; error.textContent = ""; form.reset(); ajustar(); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    error.textContent = "";
    const t = tipo.value;
    const metodo = { tipo: t, alias: alias.value.trim(), predeterminado: pred.checked };
    if (t === "tarjeta_credito" || t === "tarjeta_debito") metodo.marca = marca.value;
    if (t !== "pse") {
      if (!/^\d{4}$/.test(ultimos4.value.trim())) { error.textContent = "Escribe solo los 4 últimos dígitos."; return; }
      metodo.ultimos4 = ultimos4.value.trim();
    }
    if (t === "pse") {
      if (!banco.value.trim()) { error.textContent = "Escribe el banco."; return; }
      metodo.banco = banco.value.trim();
    }
    if (!metodo.alias) { error.textContent = "Ponle un nombre al método."; return; }
    guardar.disabled = true;
    try {
      const nuevo = await PicksyAPI.agregarMetodoPago(metodo);
      aviso("Método de pago guardado");
      await alGuardar(nuevo);
    } catch (err) {
      error.textContent = err.message;
    } finally {
      guardar.disabled = false;
    }
  });

  contenedor.append(abrir, form);
}

// ---------- estado de la membresía ----------
function pintarEstadoMembresia(m) {
  const caja = $("#estadoMembresia");
  caja.className = "estado-membresia " + (m.activa ? "activa" : "inactiva");
  caja.replaceChildren(
    el("strong", { text: m.activa ? `Membresía activa: plan ${m.plan_nombre}` : "Aún no tienes una membresía activa" }),
    el("span", {
      text: m.activa
        ? `Vence el ${new Date(m.vence_en).toLocaleDateString("es-CO", { dateStyle: "long" })} (${m.dias_restantes} día(s) restantes).`
        : (m.vence_en ? `Tu membresía venció el ${new Date(m.vence_en).toLocaleDateString("es-CO", { dateStyle: "long" })}.` : "Elige un plan para empezar."),
    }));
}

// ---------- Vista 1: elegir plan y método ----------
async function vistaCheckout() {
  mostrar("vistaCheckout");
  $("#tituloPagos").textContent = "Membresía de Picksy";
  let pagos, membresia;
  try {
    [estado.planes, estado.metodos, membresia, pagos] = await Promise.all([
      PicksyAPI.planesMembresia(), PicksyAPI.listarMetodosPago(), PicksyAPI.estadoMembresia(), PicksyAPI.listarPagos(),
    ]);
  } catch (error) {
    mensaje(error.message, true);
    return;
  }
  pintarEstadoMembresia(membresia);
  const pred = estado.metodos.find((m) => m.predeterminado) || estado.metodos[0];
  if (!estado.metodos.some((m) => m.id === estado.metodoId)) estado.metodoId = pred ? pred.id : null;
  if (!estado.planes.some((p) => p.codigo === estado.plan)) estado.plan = estado.planes[0].codigo;

  const montarFormulario = () => formularioMetodo($("#formularioMetodoCheckout"), async (nuevo) => {
    estado.metodoId = nuevo.id;
    estado.metodos = await PicksyAPI.listarMetodosPago();
    pintarMetodos();
    montarFormulario();
  });
  montarFormulario();
  pintarMetodos();
  pintarPlanes();
  pintarHistorial(pagos);
}

const metodoActual = () => estado.metodos.find((m) => m.id === estado.metodoId);
const planActual = () => estado.planes.find((p) => p.codigo === estado.plan);

function pintarPlanes() {
  const caja = $("#planesElegir");
  caja.replaceChildren();
  for (const p of estado.planes) {
    const radio = el("input", { type: "radio", name: "plan", value: p.codigo });
    radio.checked = p.codigo === estado.plan;
    const detalle = p.meses === 1 ? "Sin renovación automática" : `${pesos.format(p.valor_por_mes)} al mes`;
    const fila = el("label", { class: "opcion" + (radio.checked ? " activa" : "") }, radio,
      el("span", { class: "opcion-texto" },
        el("strong", { text: `${p.nombre} · ${p.meses} ${p.meses === 1 ? "mes" : "meses"}` }),
        el("small", { text: detalle })),
      el("span", { class: "opcion-derecha" }, pesos.format(p.valor),
        p.ahorro_porcentaje > 0 ? el("small", { text: `Ahorras ${p.ahorro_porcentaje} %` }) : ""));
    radio.addEventListener("change", () => { estado.plan = p.codigo; pintarPlanes(); });
    caja.append(fila);
  }
  pintarResumen();
}

function pintarMetodos() {
  const caja = $("#metodosElegir");
  caja.replaceChildren();
  if (!estado.metodos.length) {
    caja.append(el("p", { class: "vacio-texto", text: "Agrega un método de pago para continuar." }));
    pintarResumen();
    return;
  }
  for (const m of estado.metodos) {
    const radio = el("input", { type: "radio", name: "metodo", value: String(m.id) });
    radio.checked = m.id === estado.metodoId;
    const fila = el("label", { class: "opcion" + (radio.checked ? " activa" : "") }, radio,
      el("span", { class: "opcion-texto" }, el("strong", { text: m.descripcion }), el("small", { text: m.alias })),
      m.predeterminado ? el("span", { class: "etiqueta-pred", text: "Predeterminado" }) : "");
    radio.addEventListener("change", () => { estado.metodoId = m.id; pintarMetodos(); });
    const quitar = el("button", { type: "button", class: "button button-secondary button-mini boton-peligro", text: "Quitar", "aria-label": `Quitar ${m.descripcion}` });
    quitar.addEventListener("click", () => intentar(async () => {
      await PicksyAPI.eliminarMetodoPago(m.id);
      estado.metodos = await PicksyAPI.listarMetodosPago();
      pintarMetodos();
      aviso("Método eliminado");
    }, quitar));
    caja.append(el("div", { class: "metodo-opcion" }, fila, quitar));
  }
  pintarResumen();
}

function pintarResumen() {
  const p = planActual();
  const metodo = metodoActual();
  if (!p) return;
  filas($("#resumenPago"), [
    ["Plan", `${p.nombre} · ${p.meses} ${p.meses === 1 ? "mes" : "meses"}`],
    ["Total", pesos.format(p.valor), "total-fila"],
    ["Método", metodo ? metodo.descripcion : "—"],
  ]);
  $("#botonContinuar").disabled = !metodo;
}

function pintarHistorial(pagos) {
  const tabla = $("#tablaPagos");
  const cuerpo = tabla.querySelector("tbody");
  cuerpo.replaceChildren();
  tabla.hidden = pagos.length === 0;
  $("#sinPagos").hidden = pagos.length > 0;
  for (const p of pagos) {
    let accion = "";
    if (p.estado === "pendiente") {
      accion = el("button", { type: "button", class: "button button-primary button-mini", text: "Confirmar" });
      accion.addEventListener("click", () => { estado.pago = p; vistaConfirmar(); });
    }
    cuerpo.append(el("tr", {},
      el("td", { text: p.referencia }), el("td", { text: fecha(p.creado_en) }),
      el("td", { text: p.plan_nombre }), el("td", { text: p.metodo }),
      el("td", { text: pesos.format(p.valor) }),
      el("td", {}, el("span", { class: "etiqueta-estado " + p.estado, text: ESTADOS[p.estado] || p.estado })),
      el("td", {}, accion)));
  }
}

async function continuar() {
  const boton = $("#botonContinuar");
  const pago = await intentar(() => PicksyAPI.iniciarPago(estado.plan, estado.metodoId), boton);
  if (!pago) return;
  estado.pago = pago;
  vistaConfirmar();
}

// ---------- Vista 2: confirmar ----------
function vistaConfirmar() {
  const p = estado.pago;
  mostrar("vistaConfirmar");
  $("#tituloPagos").textContent = "Confirmar pago";
  mensaje("");
  filas($("#datosConfirmar"), [
    ["Referencia", p.referencia],
    ["Membresía", `${p.plan_nombre} · ${p.meses} ${p.meses === 1 ? "mes" : "meses"}`],
    ["Método", p.metodo],
    ["Total", pesos.format(p.valor), "total-fila"],
  ]);
  $("#venceEn").textContent = `Este pago vence el ${fecha(p.expira_en)}.`;
}

async function confirmar() {
  const boton = $("#botonConfirmarPago");
  const pago = await intentar(() => PicksyAPI.confirmarPago(estado.pago.id), boton);
  if (!pago) return;
  estado.pago = pago;
  mostrar("vistaExito");
  $("#tituloPagos").textContent = "Pago confirmado";
  filas($("#datosExito"), [
    ["Referencia", pago.referencia],
    ["Membresía", `${pago.plan_nombre} · ${pago.meses} ${pago.meses === 1 ? "mes" : "meses"}`],
    ["Total", pesos.format(pago.valor), "total-fila"],
    ["Activa hasta", new Date(pago.membresia_hasta).toLocaleDateString("es-CO", { dateStyle: "long" })],
  ]);
  try { pintarEstadoMembresia(await PicksyAPI.estadoMembresia()); } catch { /* el estado se ve al recargar */ }
}

async function cancelar() {
  const boton = $("#botonCancelarPago");
  const pago = await intentar(() => PicksyAPI.cancelarPago(estado.pago.id), boton);
  if (!pago) return;
  aviso("Pago cancelado. No se cobró nada.");
  vistaCheckout();
}

// ---------- inicio ----------
(async function iniciar() {
  if (!PicksyAPI.exigirSesion()) return;
  $("#botonContinuar").addEventListener("click", continuar);
  $("#botonConfirmarPago").addEventListener("click", confirmar);
  $("#botonCancelarPago").addEventListener("click", cancelar);
  await vistaCheckout();
})();
