const API_URL = "http://127.0.0.1:8000/api/v1";
const CLAVE_TOKEN = "picksy_token";
const CLAVE_USUARIO = "picksy_usuario";

class ErrorApi extends Error {
  constructor(mensaje, estado) {
    super(mensaje);
    this.estado = estado;
  }
}

// ---------- Almacenamiento de la sesión ----------
// "Recordar mi sesión" -> localStorage (persiste); si no, sessionStorage (se borra al cerrar la pestaña)
const Almacen = {
  leer(clave) {
    try { return localStorage.getItem(clave) || sessionStorage.getItem(clave); } catch { return null; }
  },
  guardar(clave, valor, recordar) {
    try { (recordar ? localStorage : sessionStorage).setItem(clave, valor); } catch { /* sin almacenamiento */ }
  },
  borrar(clave) {
    try { localStorage.removeItem(clave); sessionStorage.removeItem(clave); } catch { /* sin almacenamiento */ }
  },
};

function hayToken() {
  return Boolean(Almacen.leer(CLAVE_TOKEN));
}

// ---------- Petición base ----------
function mensajeDeError(datos, estado) {
  if (datos && typeof datos.detail === "string") return datos.detail;  // errores del backend en español
  if (estado === 422) return "Revisa los datos ingresados.";           // validación de FastAPI
  if (estado === 401) return "Debes iniciar sesión.";
  if (estado === 429) return "Demasiados intentos. Espera un momento e inténtalo de nuevo.";   // CAMBIO (límite de intentos)
  return "Ocurrió un error. Inténtalo de nuevo.";
}

async function peticion(ruta, { metodo = "GET", cuerpo, conToken = false } = {}) {
  const cabeceras = {};
  if (cuerpo) cabeceras["Content-Type"] = "application/json";
  if (conToken) {
    const token = Almacen.leer(CLAVE_TOKEN);
    if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  }

  let respuesta;
  try {
    respuesta = await fetch(API_URL + ruta, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo ? JSON.stringify(cuerpo) : undefined,
    });
  } catch {
    throw new ErrorApi("No se pudo conectar con el servidor. Inténtalo de nuevo.", 0);
  }

  let datos = null;
  try { datos = await respuesta.json(); } catch { /* respuesta sin cuerpo */ }

  // CAMBIO (login obligatorio): si el servidor dice que la sesión no sirve (401), se limpia y se vuelve al login.
  if (!respuesta.ok && conToken && respuesta.status === 401 && ruta !== "/auth/logout" && ruta !== "/auth/2fa/codigos-recuperacion") {
    Almacen.borrar(CLAVE_TOKEN);
    Almacen.borrar(CLAVE_USUARIO);
    window.location.replace("login.html");
  }

  if (!respuesta.ok) throw new ErrorApi(mensajeDeError(datos, respuesta.status), respuesta.status);
  // CAMBIO (paginación): el total de filas viaja en la cabecera X-Total-Count; se deja disponible en la respuesta.
  const total = respuesta.headers.get("X-Total-Count");
  if (total !== null && Array.isArray(datos)) datos.total = Number(total);
  return datos;
}


async function registrar({ nombre, correo, contrasena }) {
  // El backend ignora "nombre" hasta que se agregue esa columna; enviarlo no rompe nada.
  return peticion("/auth/registro", { metodo: "POST", cuerpo: { nombre, correo, contrasena } });
}

async function confirmarRegistro(tokenRegistro, codigo) {
  return peticion("/auth/registro/confirmar", { metodo: "POST", cuerpo: { token_registro: tokenRegistro, codigo } });
}

async function iniciarSesion(correo, contrasena, recordar = false) {
  const datos = await peticion("/auth/login", { metodo: "POST", cuerpo: { correo, contrasena } });
  // CAMBIO (2FA obligatorio): el servidor NUNCA da la sesión solo con la contraseña. Responde una de dos cosas:
  //  - { requiere_2fa: true, token_2fa }                  -> pedir el código y llamar a completarLogin2FA()
  //  - { requiere_configuracion_2fa: true, token_2fa }    -> cuenta antigua sin Authenticator: mostrar el QR
  if (datos.requiere_2fa || datos.requiere_configuracion_2fa) return datos;
  Almacen.guardar(CLAVE_TOKEN, datos.token, recordar);
  return datos;
}

// ---------- Verificación en dos pasos (2FA con Google Authenticator) ----------
// Segundo paso del login: token_2fa (lo dio iniciarSesion) + código de 6 dígitos de la app.
async function completarLogin2FA(token2fa, codigo, recordar = false) {
  const datos = await peticion("/auth/2fa/login", { metodo: "POST", cuerpo: { token_2fa: token2fa, codigo } });
  Almacen.guardar(CLAVE_TOKEN, datos.token, recordar);
  return datos;
}

// Cuentas antiguas sin Authenticator: genera la clave y el QR (data:image/svg+xml;base64,...).
async function configurarPendiente2FA(token2fa) {
  return peticion("/auth/2fa/pendiente/configurar", { metodo: "POST", cuerpo: { token_2fa: token2fa } });
}

// Cuentas antiguas: confirma con un código de la app, activa el 2FA y entra (devuelve la sesión).
async function activarPendiente2FA(token2fa, codigo, recordar = false) {
  const datos = await peticion("/auth/2fa/pendiente/activar", { metodo: "POST", cuerpo: { token_2fa: token2fa, codigo } });
  Almacen.guardar(CLAVE_TOKEN, datos.token, recordar);
  return datos;
}

async function usuarioActual() {
  if (!hayToken()) return null;
  try {
    const usuario = await peticion("/auth/me", { conToken: true });
    Almacen.guardar(CLAVE_USUARIO, JSON.stringify(usuario), Boolean(localStorage.getItem(CLAVE_TOKEN)));
    return usuario;
  } catch (error) {
    if (error.estado === 401) {          // sesión vencida o cerrada
      Almacen.borrar(CLAVE_TOKEN);
      Almacen.borrar(CLAVE_USUARIO);
      return null;
    }
    throw error;
  }
}

async function cerrarSesion() {
  try {
    if (hayToken()) await peticion("/auth/logout", { metodo: "POST", conToken: true });
  } catch { /* si falla, igual se limpia en este dispositivo */ }
  Almacen.borrar(CLAVE_TOKEN);
  Almacen.borrar(CLAVE_USUARIO);
}

// ---------- Búsqueda ----------
// tiendas: arreglo opcional, por ejemplo ["Alkosto", "Ktronix"]
// OJO: sin caché una búsqueda puede tardar hasta ~10 s; la pantalla debe mostrar "cargando".
async function buscarProductos({ producto, presupuesto, tiendas, actualizar = false }) {
  const parametros = new URLSearchParams({ producto, presupuesto: String(presupuesto) });
  if (tiendas && tiendas.length) parametros.set("tiendas", tiendas.join(","));
  if (actualizar) parametros.set("actualizar", "true");
  // CAMBIO (login obligatorio): la búsqueda exige sesión (sin token el backend responde 401).
  return peticion(`/buscar?${parametros.toString()}`, { conToken: true });
}

// ---------- Historial (requiere sesión) ----------
// CAMBIO (paginación): pagina empieza en 1. La lista devuelta trae además la propiedad .total (todas las búsquedas guardadas).
async function listarHistorial(pagina = 1, limite = 20) {
  return peticion(`/historial?pagina=${pagina}&limite=${limite}`, { conToken: true });
}

async function borrarHistorial() {
  return peticion("/historial", { metodo: "DELETE", conToken: true });
}

async function borrarBusquedaDelHistorial(id) {
  return peticion(`/historial/${id}`, { metodo: "DELETE", conToken: true });
}

async function listarTiendas() {
  return peticion("/tiendas", { conToken: true });   // CAMBIO (login obligatorio)
}

// ---------- Administración (solo rol "admin") ----------
async function listarUsuarios() {
  return peticion("/admin/usuarios", { conToken: true });
}

async function eliminarUsuario(id) {
  return peticion(`/admin/usuarios/${id}`, { metodo: "DELETE", conToken: true });
}

async function cambiarRol(id, rol) {
  return peticion(`/admin/usuarios/${id}/rol`, { metodo: "PATCH", cuerpo: { rol }, conToken: true });
}

// ---------- Recuperar contraseña ----------
// El servidor siempre responde lo mismo (exista o no el correo) y, si existe, envía un enlace al correo.
async function solicitarRecuperacion(correo) {
  return peticion("/auth/recuperar", { metodo: "POST", cuerpo: { correo } });
}

// "codigo" = código de Google Authenticator (6 dígitos) o un código de recuperación (XXXXX-XXXXX).
async function restablecerContrasena(token, contrasenaNueva, codigo) {
  return peticion("/auth/recuperar/restablecer", {
    metodo: "POST", cuerpo: { token, contrasena_nueva: contrasenaNueva, codigo },
  });
}

// ---------- Códigos de recuperación del 2FA ----------
async function regenerarCodigosRecuperacion(contrasena, codigo) {
  return peticion("/auth/2fa/codigos-recuperacion", { metodo: "POST", cuerpo: { contrasena, codigo }, conToken: true });
}

// ---------- Carritos y mochila (RF-13, RF-14, RF-17) ----------
async function listarCarritos() { return peticion("/carritos", { conToken: true }); }
async function crearCarrito(nombre, presupuesto) {
  return peticion("/carritos", { metodo: "POST", cuerpo: { nombre: nombre || null, presupuesto }, conToken: true });
}
async function verCarrito(id) { return peticion(`/carritos/${id}`, { conToken: true }); }
async function editarCarrito(id, cambios) {
  return peticion(`/carritos/${id}`, { metodo: "PATCH", cuerpo: cambios, conToken: true });
}
async function eliminarCarrito(id) { return peticion(`/carritos/${id}`, { metodo: "DELETE", conToken: true }); }

// producto = una opción de /buscar ({tienda, nombre, url, imagen, precio, envio}); prioridad de 1 a 5.
async function agregarAlCarrito(id, producto, prioridad) {
  return peticion(`/carritos/${id}/items`, {
    metodo: "POST", conToken: true,
    cuerpo: {
      tienda: producto.tienda, nombre: producto.nombre, url: producto.url, imagen: producto.imagen || null,
      precio: producto.precio, envio: producto.envio_confirmado ? producto.envio : null, prioridad,
    },
  });
}
async function cambiarPrioridad(carritoId, itemId, prioridad) {
  return peticion(`/carritos/${carritoId}/items/${itemId}`, { metodo: "PATCH", cuerpo: { prioridad }, conToken: true });
}
async function quitarDelCarrito(carritoId, itemId) {
  return peticion(`/carritos/${carritoId}/items/${itemId}`, { metodo: "DELETE", conToken: true });
}
async function optimizarCarrito(id) { return peticion(`/carritos/${id}/optimizar`, { metodo: "POST", conToken: true }); }
async function compararCarritos(a, b) { return peticion(`/carritos/comparar?a=${a}&b=${b}`, { conToken: true }); }

// ---------- Variación de precios (RF-16) ----------
async function variacionDePrecio(url) {
  return peticion(`/productos/precios?url=${encodeURIComponent(url)}`, { conToken: true });
}

// ---------- Membresía y pagos (CAMBIO pagos) ----------
// Picksy no vende los productos: lo único que se cobra es el uso de la página (membresía mensual, semestral o anual).
// MODO DEMOSTRACIÓN: el pago es simulado. Nunca se envía el número de la tarjeta, solo la marca y los últimos 4 dígitos.
async function planesMembresia() { return peticion("/pagos/planes", { conToken: true }); }
async function estadoMembresia() { return peticion("/pagos/membresia", { conToken: true }); }
async function listarMetodosPago() { return peticion("/pagos/metodos", { conToken: true }); }
async function agregarMetodoPago(metodo) { return peticion("/pagos/metodos", { metodo: "POST", cuerpo: metodo, conToken: true }); }
async function eliminarMetodoPago(id) { return peticion(`/pagos/metodos/${id}`, { metodo: "DELETE", conToken: true }); }
async function iniciarPago(plan, metodoId) {
  return peticion("/pagos", { metodo: "POST", cuerpo: { plan, metodo_id: metodoId }, conToken: true });
}
async function confirmarPago(id) { return peticion(`/pagos/${id}/confirmar`, { metodo: "POST", conToken: true }); }
async function cancelarPago(id) { return peticion(`/pagos/${id}/cancelar`, { metodo: "POST", conToken: true }); }
async function listarPagos() { return peticion("/pagos", { conToken: true }); }

// CAMBIO (login obligatorio): las páginas privadas llaman a esto; sin sesión mandan al login.
function exigirSesion() {
  if (!hayToken()) {
    window.location.replace("login.html");
    return false;
  }
  return true;
}

window.PicksyAPI = {
  registrar, iniciarSesion, usuarioActual, cerrarSesion, hayToken,
  buscarProductos, listarTiendas, ErrorApi,
  listarHistorial, borrarHistorial, borrarBusquedaDelHistorial,
  confirmarRegistro, completarLogin2FA, configurarPendiente2FA, activarPendiente2FA,
  listarUsuarios, eliminarUsuario, cambiarRol, exigirSesion,
  solicitarRecuperacion, restablecerContrasena, regenerarCodigosRecuperacion,
  listarCarritos, crearCarrito, verCarrito, editarCarrito, eliminarCarrito,
  agregarAlCarrito, cambiarPrioridad, quitarDelCarrito, optimizarCarrito, compararCarritos,
  variacionDePrecio,
  planesMembresia, estadoMembresia, listarMetodosPago, agregarMetodoPago, eliminarMetodoPago,
  iniciarPago, confirmarPago, cancelarPago, listarPagos,
};
