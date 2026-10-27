// Picksy · Conexión del frontend con el backend (FastAPI)
// Colócalo en js/api.js y cárgalo ANTES de los demás scripts:
//   <script src="js/api.js" defer></script>
//   <script src="js/login.js" defer></script>

const API_URL = "http://127.0.0.1:8000"; // cambiar cuando el backend se despliegue
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

  if (!respuesta.ok) throw new ErrorApi(mensajeDeError(datos, respuesta.status), respuesta.status);
  return datos;
}

// ---------- Cuenta ----------
async function registrar({ nombre, correo, contrasena }) {
  // El backend ignora "nombre" hasta que se agregue esa columna; enviarlo no rompe nada.
  return peticion("/auth/registro", { metodo: "POST", cuerpo: { nombre, correo, contrasena } });
}

async function iniciarSesion(correo, contrasena, recordar = false) {
  const datos = await peticion("/auth/login", { metodo: "POST", cuerpo: { correo, contrasena } });
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
  // conToken: si hay sesión, el backend guarda la búsqueda en el historial del usuario.
  // Sin sesión la búsqueda funciona igual (solo que no se guarda).
  return peticion(`/buscar?${parametros.toString()}`, { conToken: true });
}

// ---------- Historial (requiere sesión) ----------
async function listarHistorial() {
  return peticion("/historial", { conToken: true });
}

async function borrarHistorial() {
  return peticion("/historial", { metodo: "DELETE", conToken: true });
}

async function borrarBusquedaDelHistorial(id) {
  return peticion(`/historial/${id}`, { metodo: "DELETE", conToken: true });
}

async function listarTiendas() {
  return peticion("/tiendas");
}

window.PicksyAPI = {
  registrar, iniciarSesion, usuarioActual, cerrarSesion, hayToken,
  buscarProductos, listarTiendas, ErrorApi,
  listarHistorial, borrarHistorial, borrarBusquedaDelHistorial,
};
