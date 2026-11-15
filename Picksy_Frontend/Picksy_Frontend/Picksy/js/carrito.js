const MAX_CARRITOS = 5;
const $ = (s) => document.querySelector(s);

const pesos = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0
});

const PRIORIDADES = [
  [5, "5 · Indispensable"],
  [4, "4 · Muy importante"],
  [3, "3 · Importante"],
  [2, "2 · Deseable"],
  [1, "1 · Opcional"]
];

let carritos = [];
let activo = null;
let resultado = null;
let carritoPendienteEliminar = null;

function actualizarLimiteCarritos() {
  const botonCrear = $("#formNuevo button[type='submit']");
  const aviso = $("#limiteCarritos");

  const limiteAlcanzado = carritos.length >= MAX_CARRITOS;

  if (botonCrear) {
    botonCrear.disabled = limiteAlcanzado;
  }

  if (aviso) {
    aviso.textContent = limiteAlcanzado
      ? `Has alcanzado el límite de ${MAX_CARRITOS} carritos. Elimina uno para crear otro.`
      : `Tienes ${MAX_CARRITOS - carritos.length} espacio(s) disponible(s).`;
  }
}

// ---------- utilidades ----------

function mensaje(texto, esError = false) {
  const f = $("#carritoFeedback");
  if (!f) return;

  f.textContent = texto;
  f.style.color = esError ? "#B54E51" : "#65854C";
}

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

function urlSegura(valor) {
  try {
    const u = new URL(valor);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : "";
  } catch {
    return "";
  }
}

const nombreDe = (c) => c.nombre || `Carrito ${c.id}`;

function dato(titulo, valor) {
  return el(
    "div",
    {},
    el("span", { text: titulo }),
    el("strong", { text: valor })
  );
}

// ---------- modal de eliminación ----------

const modalEliminar = $("#eliminarCarritoModal");
const botonConfirmarEliminar = $("#confirmarEliminar");

function abrirModalEliminar(carrito) {
  if (!modalEliminar || !botonConfirmarEliminar) {
    mensaje("No se pudo abrir la ventana de confirmación.", true);
    return;
  }

  carritoPendienteEliminar = carrito;

  $("#eliminarCarritoMensaje").textContent =
    `¿Estás seguro de que deseas eliminar «${nombreDe(carrito)}»? ` +
    "También se eliminarán todos los productos que contiene. Esta acción no se puede deshacer.";

  modalEliminar.classList.remove("hidden");
  botonConfirmarEliminar.focus();
}

function cerrarModalEliminar() {
  if (!modalEliminar || botonConfirmarEliminar?.disabled) return;

  modalEliminar.classList.add("hidden");
  carritoPendienteEliminar = null;
}

$("#cerrarEliminarModal")?.addEventListener("click", cerrarModalEliminar);
$("#cancelarEliminar")?.addEventListener("click", cerrarModalEliminar);

modalEliminar?.addEventListener("click", (event) => {
  if (event.target === modalEliminar) {
    cerrarModalEliminar();
  }
});

document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    modalEliminar &&
    !modalEliminar.classList.contains("hidden")
  ) {
    cerrarModalEliminar();
  }
});

botonConfirmarEliminar?.addEventListener("click", async () => {
  if (!carritoPendienteEliminar) return;

  const carrito = carritoPendienteEliminar;

  botonConfirmarEliminar.disabled = true;
  botonConfirmarEliminar.textContent = "Eliminando...";

  try {
    await PicksyAPI.eliminarCarrito(carrito.id);

    // Cierra el modal después de confirmar la eliminación.
    modalEliminar.classList.add("hidden");
    carritoPendienteEliminar = null;

    activo = null;
    resultado = null;

    mensaje("Carrito eliminado correctamente.");

    await cargarLista();

  } catch (error) {
    mensaje(error.message || "No se pudo eliminar el carrito.", true);

  } finally {
    botonConfirmarEliminar.disabled = false;
    botonConfirmarEliminar.textContent = "Sí, eliminar carrito";
  }
});

// ---------- lista de carritos ----------

async function cargarLista(abrir) {
  carritos = await PicksyAPI.listarCarritos();
  actualizarLimiteCarritos();
  const lista = $("#listaCarritos");

  lista.replaceChildren(
    ...carritos.map((c) => {
      const boton = el(
        "button",
        {
          type: "button",
          class: "carrito-fila" + (c.id === activo ? " activo" : "")
        },
        el("strong", { text: nombreDe(c) }),
        el("span", {
          text: `${c.productos} producto(s) · ${pesos.format(c.total)} de ${pesos.format(c.presupuesto)}`
        })
      );

      boton.addEventListener("click", () => abrirCarrito(c.id));

      return el("li", {}, boton);
    })
  );

  if (carritos.length === 0) {
    lista.append(
      el("li", {
        class: "vacio-texto",
        text: "Todavía no tienes carritos."
      })
    );
  }

  // Actualiza las opciones de comparación.
  for (const id of ["#compA", "#compB"]) {
    const s = $(id);
    const anterior = s.value;

    s.replaceChildren(
      ...carritos.map((c) =>
        el("option", {
          value: String(c.id),
          text: nombreDe(c)
        })
      )
    );

    if (anterior) s.value = anterior;
  }

  // Evita comparar un carrito consigo mismo.
  const compA = $("#compA");
  const compB = $("#compB");

  if (compA.value === compB.value) {
    const otro = carritos.find(
      (c) => String(c.id) !== compA.value
    );

    if (otro) compB.value = String(otro.id);
  }

  $("#compararCaja").classList.toggle(
    "hidden",
    carritos.length < 2
  );

  // Abre el carrito correspondiente.
  if (abrir !== undefined) {
    await abrirCarrito(abrir);

  } else if (activo && carritos.some((c) => c.id === activo)) {
    await abrirCarrito(activo);

  } else if (carritos.length > 0) {
    await abrirCarrito(carritos[0].id);

  } else {
    activo = null;
    resultado = null;
    pintarVacio();
  }
}

function pintarVacio() {
  $("#detalle").replaceChildren(
    el("p", {
      class: "vacio-texto",
      text: "Crea un carrito o elige uno de la lista. Para agregar productos, haz una búsqueda y pulsa «+ Carrito» en el que te guste."
    })
  );
}

// ---------- detalle del carrito ----------

async function abrirCarrito(id) {
  if (id !== activo) resultado = null;

  activo = id;

  document.querySelectorAll(".carrito-fila").forEach((b, i) => {
    b.classList.toggle(
      "activo",
      carritos[i]?.id === id
    );
  });

  try {
    const c = await PicksyAPI.verCarrito(id);
    pintarDetalle(c);

  } catch (error) {
    mensaje(error.message || "No se pudo abrir el carrito.", true);
  }
}

function pintarDetalle(c) {
  const caja = $("#detalle");
  const items = c.items;

  // Cabecera y presupuesto.
  const inputPresupuesto = el("input", {
    type: "number",
    min: "1",
    step: "1",
    value: String(c.presupuesto),
    "aria-label": "Presupuesto",
    style: "max-width:150px"
  });

  const guardarPres = el("button", {
    type: "button",
    class: "button button-secondary button-mini",
    text: "Cambiar presupuesto"
  });

  guardarPres.addEventListener("click", async () => {
    try {
      const v = Number(inputPresupuesto.value);

      if (!(v > 0)) {
        throw new Error("El presupuesto debe ser mayor que cero.");
      }

      await PicksyAPI.editarCarrito(c.id, {
        presupuesto: v
      });

      resultado = null;

      mensaje("Presupuesto actualizado. Vuelve a calcular la mejor combinación.");

      await cargarLista(c.id);

    } catch (error) {
      mensaje(error.message, true);
    }
  });

  // Botón de eliminación: abre el modal personalizado.
  const eliminar = el("button", {
    type: "button",
    class: "button button-secondary boton-peligro",
    text: "Eliminar carrito"
  });

  eliminar.addEventListener("click", () => {
    abrirModalEliminar(c);
  });

  // CAMBIO (pagos): lleva a la ventana de pagos (membresía de Picksy).
  const pagar = el("a", {
    href: "pago.html",
    class: "button button-primary button-mini",
    text: "Membresía"
  });

  const cabecera = el(
    "div",
    { class: "carrito-cabecera" },
    el("h2", { text: nombreDe(c) }),
    el(
      "div",
      { class: "carrito-acciones" },
      inputPresupuesto,
      guardarPres,
      pagar,
      eliminar
    )
  );

  // Resumen del carrito.
  const barra = el(
    "div",
    { class: "resumen-barra" },
    dato("Presupuesto", pesos.format(c.presupuesto)),
    dato(
      c.optimizado ? "Total de lo elegido" : "Total de la lista",
      pesos.format(c.total)
    ),
    dato("Productos", String(c.productos)),
    dato(
      c.optimizado ? "Prioridad lograda" : "Prioridad de la lista",
      String(c.prioridad_total)
    )
  );

  // Tabla de productos.
  let tabla;

  if (items.length === 0) {
    tabla = el("p", {
      class: "vacio-texto",
      text: "Este carrito está vacío. Busca un producto y pulsa «+ Carrito»."
    });

  } else {
    const cuerpo = el("tbody");

    for (const i of items) {
      const enlace = urlSegura(i.url);

      const nombre = el(
        "td",
        { class: "nombre" },
        enlace
          ? el("a", {
            href: enlace,
            target: "_blank",
            rel: "noopener noreferrer",
            text: i.nombre
          })
          : el("span", { text: i.nombre }),
        el("small", { text: i.tienda })
      );

      // Selector de prioridad.
      const sel = el("select", {
        "aria-label": "Prioridad"
      });

      for (const [v, t] of PRIORIDADES) {
        sel.append(
          el("option", {
            value: String(v),
            text: t
          })
        );
      }

      sel.value = String(i.prioridad);

      sel.addEventListener("change", async () => {
        try {
          await PicksyAPI.cambiarPrioridad(
            c.id,
            i.id,
            Number(sel.value)
          );

          resultado = null;

          mensaje("Prioridad actualizada. Vuelve a calcular la mejor combinación.");

          await cargarLista(c.id);

        } catch (error) {
          mensaje(error.message, true);
        }
      });

      // Historial de precios.
      const precio = el("button", {
        type: "button",
        class: "button button-secondary button-mini",
        text: "Precio"
      });

      precio.title = "Ver cómo ha cambiado el precio";

      precio.addEventListener("click", () => {
        PicksyUI.mostrarVariacion(i.url, i.nombre);
      });

      // Quitar producto.
      const quitar = el("button", {
        type: "button",
        class: "button button-secondary button-mini boton-peligro",
        text: "Quitar"
      });

      quitar.addEventListener("click", async () => {
        try {
          await PicksyAPI.quitarDelCarrito(c.id, i.id);

          resultado = null;

          await cargarLista(c.id);

        } catch (error) {
          mensaje(error.message, true);
        }
      });

      // Estado de optimización.
      const estado = c.optimizado
        ? el("span", {
          class: "etiqueta-estado " + (i.incluido ? "dentro" : "fuera"),
          text: i.incluido ? "Dentro" : "Fuera"
        })
        : el("span", {
          class: "muted",
          text: "—"
        });

      const fila = el(
        "tr",
        {
          class: c.optimizado && !i.incluido ? "fuera" : ""
        },
        nombre,
        el("td", {
          text: pesos.format(i.precio_total)
        }),
        el("td", {}, sel),
        el("td", {}, estado),
        el(
          "td",
          {},
          el("div", { class: "carrito-acciones" }, precio, quitar)
        )
      );

      cuerpo.append(fila);
    }

    tabla = el(
      "div",
      { class: "tabla-caja" },
      el(
        "table",
        { class: "tabla-items" },
        el(
          "thead",
          {},
          el(
            "tr",
            {},
            ...["Producto", "Precio + envío", "Prioridad", "Mochila", ""]
              .map((t) => el("th", { text: t }))
          )
        ),
        cuerpo
      )
    );
  }

  // Optimización.
  const calcular = el("button", {
    type: "button",
    class: "button button-primary",
    text: "Calcular mejor combinación"
  });

  calcular.disabled = items.length === 0;

  calcular.addEventListener("click", async () => {
    calcular.disabled = true;

    try {
      resultado = await PicksyAPI.optimizarCarrito(c.id);

      mensaje("");

      await cargarLista(c.id);

    } catch (error) {
      mensaje(error.message, true);
      calcular.disabled = false;
    }
  });

  const partes = [
    cabecera,
    barra,
    tabla,
    el("div", {
      style: "margin-top:14px"
    }, calcular)
  ];

  // Resultado de la optimización.
  if (
    c.optimizado &&
    resultado &&
    resultado.carrito.id === c.id
  ) {
    const caja2 = el(
      "div",
      {
        class: "resultado-mochila" +
          (
            resultado.incluidos.length === 0 && c.productos > 0
              ? " vacio"
              : ""
          )
      },
      el("strong", {
        text: resultado.mensaje
      }),
      el("div", {
        text: `Total ${pesos.format(resultado.total)} de ${pesos.format(resultado.presupuesto)} · te sobran ${pesos.format(resultado.sobrante)} · prioridad lograda: ${resultado.prioridad_total}`
      })
    );

    partes.push(caja2);

  } else if (c.optimizado) {
    partes.push(
      el(
        "div",
        { class: "resultado-mochila" },
        el("strong", {
          text: "Este carrito ya fue calculado."
        }),
        el("div", {
          text: "Los productos marcados «Dentro» son la mejor combinación que cabe en el presupuesto."
        })
      )
    );
  }

  caja.replaceChildren(...partes);
}

// ---------- crear carrito ----------

$("#formNuevo").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (carritos.length >= MAX_CARRITOS) {
    mensaje(
      `No puedes crear más de ${MAX_CARRITOS} carritos. Elimina uno para continuar.`,
      true
    );
    return;
  }
  const presupuesto = Number($("#nuevoPresupuesto").value);

  if (!(presupuesto > 0)) {
    mensaje("Escribe un presupuesto mayor que cero.", true);
    return;
  }

  try {
    const nuevo = await PicksyAPI.crearCarrito(
      $("#nuevoNombre").value.trim(),
      presupuesto
    );

    $("#nuevoNombre").value = "";
    $("#nuevoPresupuesto").value = "";

    mensaje("Carrito creado.");

    await cargarLista(nuevo.id);

  } catch (error) {
    mensaje(error.message, true);
  }
});

// ---------- comparar carritos (RF-17) ----------

$("#botonComparar").addEventListener("click", async () => {
  const a = Number($("#compA").value);
  const b = Number($("#compB").value);
  const salida = $("#compararResultado");

  if (!a || !b || a === b) {
    mensaje("Selecciona dos carritos diferentes para comparar.", true);
    return;
  }

  try {
    const r = await PicksyAPI.compararCarritos(a, b);

    const tarjeta = (x, gana) =>
      el(
        "div",
        {
          class: "comparar-tarjeta" + (gana ? " ganador" : "")
        },
        el("span", {
          text: nombreDe(x)
        }),
        el("strong", {
          class: "total",
          text: pesos.format(x.total)
        }),
        el("span", {
          text: `${x.productos} producto(s) · prioridad ${x.prioridad_total}${x.optimizado ? " · calculado" : ""}`
        })
      );

    salida.replaceChildren(
      tarjeta(r.a, r.mas_barato === "a"),
      tarjeta(r.b, r.mas_barato === "b"),
      el("p", {
        class: "comparar-mensaje",
        text: r.mensaje + (
          r.diferencia
            ? ` Diferencia: ${pesos.format(r.diferencia)}.`
            : ""
        )
      })
    );

    salida.classList.remove("hidden");
    mensaje("");

  } catch (error) {
    mensaje(error.message, true);
  }
});

// ---------- inicialización ----------

(async function iniciar() {
  if (typeof PicksyAPI === "undefined") {
    mensaje("No se pudo cargar la conexión con el servidor.", true);
    return;
  }

  try {
    const yo = await PicksyAPI.usuarioActual();

    if (!yo) {
      window.location.replace("login.html");
      return;
    }

    await cargarLista();

  } catch (error) {
    mensaje(
      error.message || "No se pudieron cargar tus carritos.",
      true
    );
  }
})();
