// Picksy - interacciones iniciales del frontend.

const state = {
  query: "",
  category: "Todos",
  view: "buscar",
  history: []
};

const $ = (selector) => document.querySelector(selector);

function showToast(message) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function recordSearch(query, presupuesto) { // CAMBIO (backend): ahora también guarda el presupuesto
  if (!query.trim()) return;
  state.history.unshift({
    query: query.trim(),
    presupuesto: presupuesto || null,
    date: new Date().toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" })
  });
  state.history = state.history.slice(0, 15);
  renderHistory();
}

function setView(view) {
  state.view = view;
  $("#searchView")?.classList.toggle("hidden", view !== "buscar");
  $("#hero")?.classList.toggle("hidden", view !== "buscar");
  $("#historyView")?.classList.toggle("hidden", view !== "historial");
  $("#productDetail")?.classList.add("hidden");
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  if (view === "historial") renderHistory();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderHistory() {
  const list = $("#historyList");
  if (!list) return;
  list.innerHTML = state.history.map((item) => `
    <div class="history-item">
      <div><strong>${escapeHtml(item.query)}</strong><br><span>${item.presupuesto ? "Presupuesto: " + formatoPesos.format(item.presupuesto) : "Búsqueda realizada"}</span></div>
      <span>${escapeHtml(item.date)}</span>
      <button class="button button-secondary" data-research="${escapeHtml(item.query)}" data-budget="${item.presupuesto || ""}">Buscar otra vez</button>
    </div>`).join("");
  $("#historyEmpty")?.classList.toggle("hidden", state.history.length > 0);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

// ===== CAMBIO (backend): búsqueda conectada con el backend (js/api.js) =====
// Requiere que js/api.js esté cargado en index.html ANTES de este archivo,
// y los elementos #budgetInput, #searchStatus y #searchNotices del index.html.

let ultimosResultados = null; // última respuesta de /buscar; permite reordenar sin volver a consultar
let numeroBusqueda = 0;       // sirve para ignorar respuestas viejas si el usuario busca otra vez

const formatoPesos = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

function leerPresupuesto() {
  // El campo #budgetInput es de tipo "number": su valor ya viene como "300000" (sin puntos).
  const valor = Number(($("#budgetInput")?.value || "").trim());
  return Number.isFinite(valor) && valor > 0 ? valor : null;
}

// Solo se aceptan enlaces http/https: los datos vienen de páginas de terceros.
function urlSegura(valor) {
  try {
    const url = new URL(valor);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

function mostrarEstado(mensaje, tipo = "") {
  const estado = $("#searchStatus");
  if (!estado) return;
  estado.textContent = mensaje;
  estado.className = "search-status" + (tipo ? " " + tipo : "") + (mensaje ? "" : " hidden");
}

function mostrarAvisos(avisos) {
  const caja = $("#searchNotices");
  if (!caja) return;
  const hay = Array.isArray(avisos) && avisos.length > 0;
  caja.textContent = hay ? "Aviso: " + avisos.join(" · ") : "";
  caja.classList.toggle("hidden", !hay);
}

function opciones(cantidad) {
  return cantidad === 1 ? "1 opción" : `${cantidad} opciones`;
}

function textoEnvio(opcion) {
  if (!opcion.envio_confirmado) return "Envío por calcular";
  return opcion.envio === 0 ? "Envío gratis" : `+ envío ${formatoPesos.format(opcion.envio)}`;
}

function textoFecha(iso) {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return "";
  return "Act. " + fecha.toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}

function tarjetaProducto(opcion, esMejor) {
  const imagen = urlSegura(opcion.imagen);
  const enlace = urlSegura(opcion.url);
  const visual = imagen && !imagen.includes("no_image")
    ? `<img src="${escapeHtml(imagen)}" alt="${escapeHtml(opcion.nombre)}" loading="lazy" referrerpolicy="no-referrer">`
    : `<span class="product-emoji">🛍️</span>`;
  const boton = enlace
    ? `<a class="button button-primary" href="${escapeHtml(enlace)}" target="_blank" rel="noopener noreferrer">Ver en ${escapeHtml(opcion.tienda)} →</a>`
    : "";
  return `
    <article class="product-card">
      <div class="product-visual">
        ${esMejor ? '<span class="product-badge">Mejor precio</span>' : ""}
        ${visual}
      </div>
      <div class="product-info">
        <span class="product-category">${escapeHtml(opcion.tienda)}</span>
        <h3>${escapeHtml(opcion.nombre)}</h3>
        <div class="product-price">${formatoPesos.format(opcion.total)}</div>
        <div class="product-meta">
          <span>${escapeHtml(textoEnvio(opcion))}</span>
          <span>${escapeHtml(textoFecha(opcion.actualizado_en))}</span>
        </div>
        <div class="card-actions">${boton}</div>
      </div>
    </article>`;
}

function ordenar(lista) {
  const orden = $("#sortSelect")?.value || "recommended";
  const copia = [...lista];
  if (orden === "low") copia.sort((a, b) => a.total - b.total);
  if (orden === "high") copia.sort((a, b) => b.total - a.total);
  return copia; // "recommended" conserva el orden del backend (de menor a mayor total)
}

function mostrarResultados() {
  const datos = ultimosResultados;
  const grid = $("#productGrid");
  const vacio = $("#emptyState");
  if (!datos || !grid) return;

  const viables = ordenar(datos.viables);
  const claveMejor = datos.mejor_opcion ? datos.mejor_opcion.tienda + "|" + datos.mejor_opcion.url : null;
  grid.innerHTML = viables.map((o) => tarjetaProducto(o, claveMejor === o.tienda + "|" + o.url)).join("");

  $("#resultsTitle").textContent = `Resultados para «${datos.producto}»`;
  const presupuestoTexto = formatoPesos.format(datos.presupuesto);
  if (viables.length > 0) {
    const sobran = datos.descartadas.length;
    $("#resultsSubtitle").textContent =
      `${opciones(viables.length)} dentro de tu presupuesto de ${presupuestoTexto}.` +
      (sobran ? ` ${sobran === 1 ? "Otra supera" : `Otras ${sobran} superan`} tu presupuesto.` : "");
  } else {
    $("#resultsSubtitle").textContent = `Tu presupuesto: ${presupuestoTexto}.`;
  }

  vacio?.classList.toggle("hidden", viables.length > 0);
  if (viables.length === 0 && vacio) {
    const titulo = vacio.querySelector("h3");
    const texto = vacio.querySelector("p");
    if (datos.descartadas.length > 0) {
      if (titulo) titulo.textContent = "Ninguna opción cabe en tu presupuesto";
      if (texto) texto.textContent =
        `Encontramos ${opciones(datos.descartadas.length)}, pero la más barata cuesta ${formatoPesos.format(datos.descartadas[0].total)}. Prueba con un presupuesto mayor.`;
    } else {
      if (titulo) titulo.textContent = "No encontramos productos";
      if (texto) texto.textContent = `No encontramos «${datos.producto}» en las tiendas consultadas. Prueba con otro nombre.`;
    }
  }
}

async function buscarEnBackend(producto, presupuesto) {
  if (typeof PicksyAPI === "undefined") {
    mostrarEstado("Falta cargar js/api.js en index.html.", "error");
    return;
  }
  const numero = ++numeroBusqueda;
  const boton = $("#searchForm button[type='submit']");
  if (boton) boton.disabled = true;

  mostrarAvisos([]);
  $("#productGrid").innerHTML = "";
  $("#emptyState")?.classList.add("hidden");
  mostrarEstado(`Buscando «${producto}» en las tiendas… la primera búsqueda puede tardar unos segundos.`, "loading");

  try {
    const datos = await PicksyAPI.buscarProductos({ producto, presupuesto });
    if (numero !== numeroBusqueda) return; // llegó tarde: ya hay otra búsqueda en curso
    ultimosResultados = datos;
    mostrarEstado("");
    mostrarAvisos(datos.avisos);
    mostrarResultados();
    if (haySesion()) cargarHistorial(); // el backend ya guardó esta búsqueda
  } catch (error) {
    if (numero !== numeroBusqueda) return;
    mostrarEstado(error.message || "No se pudo completar la búsqueda.", "error");
  } finally {
    if (boton && numero === numeroBusqueda) boton.disabled = false;
  }
}

// CAMBIO (backend): si la imagen de una tienda no carga (bloqueo, enlace roto o imagen de relleno),
// se cambia por el ícono 🛍️ en vez de mostrar el texto del nombre del producto.
// El evento "error" de una imagen no sube por el DOM, por eso se escucha en la fase de captura.
$("#productGrid")?.addEventListener("error", (event) => {
  const imagen = event.target;
  if (!(imagen instanceof HTMLImageElement)) return;
  const marco = imagen.parentElement;
  imagen.remove();
  if (marco && !marco.querySelector(".product-emoji")) {
    marco.insertAdjacentHTML("beforeend", '<span class="product-emoji">🛍️</span>');
  }
}, true);

function limpiarBusqueda() {
  numeroBusqueda++; // cancela cualquier búsqueda en curso
  ultimosResultados = null;
  $("#searchInput").value = "";
  $("#productGrid").innerHTML = "";
  $("#emptyState")?.classList.add("hidden");
  mostrarEstado("");
  mostrarAvisos([]);
  $("#resultsTitle").textContent = "Productos destacados";
  $("#resultsSubtitle").textContent = "Una selección para ayudarte a elegir mejor.";
  const boton = $("#searchForm button[type='submit']");
  if (boton) boton.disabled = false;
}

$("#clearSearch")?.addEventListener("click", limpiarBusqueda);

$("#searchForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.query = $("#searchInput").value.trim();

  // CAMBIO (backend): ahora hacen falta un producto (mínimo 2 caracteres) y un presupuesto.
  if (state.query.length < 2) {
    showToast("Escribe qué producto buscas.");
    $("#searchInput").focus();
    return;
  }
  // CAMBIO (backend): la validación y el guardado del presupuesto están en validarPresupuesto()
  // (sección "PRESUPUESTO DEL USUARIO", más abajo). Devuelve el número, o null si no es válido.
  const presupuesto = validarPresupuesto();
  if (presupuesto === null) {
    budgetInput.focus();
    return;
  }

  // CAMBIO (backend): con sesión iniciada el historial lo guarda el backend (se recarga al terminar la búsqueda);
  // como visitante sigue guardándose solo en esta visita.
  if (!haySesion()) recordSearch(state.query, presupuesto);
  setView("buscar");
  $("#searchView")?.scrollIntoView({ behavior: "smooth", block: "start" });
  await buscarEnBackend(state.query, presupuesto);
});

document.querySelectorAll(".search-chip").forEach((button) => {
  button.addEventListener("click", () => {
    $("#searchInput").value = button.dataset.query;
    $("#searchForm").requestSubmit();
  });
});

// ============================================
// PRESUPUESTO DEL USUARIO - PICKSY
// ============================================

// Clave con la que guardamos el presupuesto en el navegador.
// Puedes buscar "picksyPresupuesto" para localizar este dato.
const CLAVE_PRESUPUESTO = "picksyPresupuesto";

// Recuperamos los elementos del buscador de index.html.
const searchForm = document.getElementById("searchForm");
const searchInput = document.getElementById("searchInput");
const budgetInput = document.getElementById("budgetInput");
const searchFeedback = document.getElementById("searchFeedback");

// Al cargar la página, recuperamos el presupuesto guardado.
const presupuestoGuardado = localStorage.getItem(CLAVE_PRESUPUESTO);

if (presupuestoGuardado !== null) {
    budgetInput.value = presupuestoGuardado;
}

// Cuando el usuario pulsa "Buscar", leemos ambos campos.
// CAMBIO (backend): antes esto era un segundo manejador del evento "submit". Ahora es una función
// que el manejador de arriba (el que llama al backend) usa para validar y guardar el presupuesto;
// así el formulario tiene un solo manejador y no se hacen dos cosas a la vez.
function validarPresupuesto() {
    const producto = searchInput.value.trim();
    const presupuestoTexto = budgetInput.value.trim();

    // Validamos que el presupuesto sea un número positivo.
    if (
        presupuestoTexto !== "" &&
        (!Number.isFinite(Number(presupuestoTexto)) ||
         Number(presupuestoTexto) <= 0)
    ) {
        searchFeedback.textContent =
            "Ingresa un presupuesto mayor que cero.";
        return null;
    }

    // CAMBIO (backend): el backend necesita un presupuesto para filtrar los resultados,
    // así que ya no se permite buscar con el campo vacío.
    if (presupuestoTexto === "") {
        localStorage.removeItem(CLAVE_PRESUPUESTO);
        searchFeedback.textContent =
            "Escribe tu presupuesto en pesos, por ejemplo 300000.";
        return null;
    }

    // Convertimos el presupuesto de texto a número.
    const presupuesto = presupuestoTexto === ""
        ? null
        : Number(presupuestoTexto);

    // ============================================
    // AQUÍ SE GUARDA EL PRESUPUESTO
    // localStorage conserva el dato en este navegador.
    // Si el usuario deja el campo vacío, eliminamos
    // el presupuesto guardado anteriormente.
    // ============================================
    if (presupuesto === null) {
        localStorage.removeItem(CLAVE_PRESUPUESTO);
    } else {
        localStorage.setItem(
            CLAVE_PRESUPUESTO,
            String(presupuesto)
        );
    }

    // Datos disponibles para utilizarlos en la búsqueda.
    // producto: nombre del artículo.
    // presupuesto: valor numérico o null si no se indicó.
    console.log("Producto buscado:", producto);
    console.log("Presupuesto máximo:", presupuesto);

    // Mensaje de confirmación del presupuesto.
    if (presupuesto !== null) {
        searchFeedback.textContent =
            `Presupuesto establecido: $${presupuesto.toLocaleString("es-CO")}.`;
    } else {
        searchFeedback.textContent =
            "Buscarás sin un límite de presupuesto.";
    }

    // CAMBIO (backend): la búsqueda real se hace en el manejador de "submit" de arriba (buscarEnBackend),
    // que envía "producto" y "presupuesto" al backend.
    return presupuesto;
}

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.querySelectorAll(".category-pill").forEach((button) => {
  button.addEventListener("click", () => {
    state.category = button.dataset.category;
    document.querySelectorAll(".category-pill").forEach((pill) => {
      pill.classList.toggle("active", pill === button);
    });
    // CAMBIO (backend): el backend todavía no filtra por categoría.
    if (state.category !== "Todos") {
      showToast("Por ahora las categorías no filtran los resultados.");
    }
  });
});

$("#sortSelect")?.addEventListener("change", () => {
  // CAMBIO (backend): con resultados reales se reordenan sin volver a consultar al backend.
  if (!ultimosResultados) {
    showToast("El ordenamiento estará disponible cuando haya productos.");
    return;
  }
  mostrarResultados();
});

$("#clearHistory")?.addEventListener("click", async () => {
  // CAMBIO (backend): con sesión también se borra en el servidor.
  if (haySesion()) {
    try {
      await PicksyAPI.borrarHistorial();
    } catch (error) {
      showToast(error.message || "No se pudo borrar el historial.");
      return;
    }
  }
  state.history = [];
  renderHistory();
});

$("#backToSearch")?.addEventListener("click", () => setView("buscar"));

$("#bannerSearch")?.addEventListener("click", () => {
  setView("buscar");
  $("#searchInput")?.focus();
});

$("#historyList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-research]");
  if (!button) return;
  $("#searchInput").value = button.dataset.research;
  // CAMBIO (backend): también se recupera el presupuesto de esa búsqueda.
  if (button.dataset.budget && $("#budgetInput")) $("#budgetInput").value = Number(button.dataset.budget);
  $("#searchForm").requestSubmit();
});

renderHistory();

// CAMBIO (backend): historial guardado en el backend (solo con sesión iniciada).
function haySesion() {
  return typeof PicksyAPI !== "undefined" && PicksyAPI.hayToken();
}

async function cargarHistorial() {
  if (!haySesion()) return;
  try {
    const filas = await PicksyAPI.listarHistorial();
    state.history = filas.map((fila) => ({
      query: fila.termino,
      presupuesto: fila.presupuesto,
      date: new Date(fila.creado_en).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" }),
    }));
    renderHistory();
  } catch {
    // Si falla (sesión vencida o sin conexión), se deja el historial de esta visita.
  }
}

// CAMBIO (backend): sesión del usuario.
// Si hay una sesión iniciada (token guardado por js/api.js), reemplaza "¡Hola, visitante!"
// por el nombre del usuario y convierte el avatar en un botón para cerrar sesión.
// Requiere que js/api.js esté cargado en index.html ANTES de este archivo.
async function cargarSesion() {
  const saludo = document.querySelector(".user-greeting");
  const avatar = document.querySelector(".avatar");
  if (!saludo || !avatar || typeof PicksyAPI === "undefined") return;

  try {
    const usuario = await PicksyAPI.usuarioActual();
    if (!usuario) return; // sin sesión: se queda como visitante

    // Por ahora el backend solo guarda el correo; se muestra la parte anterior al "@".
    const nombre = usuario.correo.split("@")[0];
    saludo.textContent = `¡Hola, ${nombre}!`;
    cargarHistorial(); // trae el historial guardado en el backend
    avatar.textContent = nombre.charAt(0).toUpperCase();
    avatar.href = "#";
    avatar.title = "Cerrar sesión";
    avatar.setAttribute("aria-label", "Cerrar sesión");
    avatar.addEventListener("click", async (event) => {
      event.preventDefault();
      if (!window.confirm("¿Quieres cerrar sesión?")) return;
      await PicksyAPI.cerrarSesion();
      window.location.reload();
    });
  } catch {
    // Sin conexión con el backend: la página sigue funcionando como visitante.
  }
}

cargarSesion();