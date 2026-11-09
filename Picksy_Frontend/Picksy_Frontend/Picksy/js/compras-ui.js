// CAMBIO (backend): ventanas compartidas por index.html y carrito.html.
//   PicksyUI.elegirCarrito(opcion)        -> "Agregar al carrito": elegir carrito (o crear uno) y la prioridad de 1 a 5 (RF-13).
//   PicksyUI.mostrarVariacion(url, nombre) -> cuánto ha cambiado el precio de un producto con el tiempo (RF-16).
// Requiere js/api.js cargado antes. Todo el texto que viene del servidor se inserta con textContent (nunca como HTML).

(function () {
  const pesos = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

  const PRIORIDADES = [
    [5, "5 · Indispensable"], [4, "4 · Muy importante"], [3, "3 · Importante"], [2, "2 · Deseable"], [1, "1 · Opcional"],
  ];

  function aviso(texto) {
    if (typeof showToast === "function") return showToast(texto);   // el aviso de index.html
    let t = document.querySelector("#toast");
    if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
    t.textContent = texto;
    t.classList.add("show");
    window.clearTimeout(aviso.timer);
    aviso.timer = window.setTimeout(() => t.classList.remove("show"), 2600);
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

  function crearDialogo(titulo) {
    const dialogo = el("dialog", { class: "dialogo" });
    const cerrar = el("button", { type: "button", class: "dialogo-cerrar", "aria-label": "Cerrar", text: "×" });
    cerrar.addEventListener("click", () => dialogo.close());
    dialogo.append(cerrar, el("h3", { text: titulo }));
    dialogo.addEventListener("close", () => dialogo.remove());
    dialogo.addEventListener("click", (e) => { if (e.target === dialogo) dialogo.close(); });
    document.body.appendChild(dialogo);
    return dialogo;
  }

  // ---------- Agregar al carrito ----------
  async function elegirCarrito(opcion) {
    const dialogo = crearDialogo("Agregar al carrito");
    dialogo.append(el("p", { class: "muted", text: opcion.nombre }),
      el("p", { class: "dialogo-precio", text: pesos.format(opcion.total) + " · " + opcion.tienda }));
    const cuerpo = el("div", { class: "dialogo-cuerpo" }, el("p", { class: "muted", text: "Cargando tus carritos..." }));
    dialogo.append(cuerpo);
    dialogo.showModal();

    let carritos;
    try {
      carritos = await PicksyAPI.listarCarritos();
    } catch (error) {
      cuerpo.replaceChildren(el("p", { class: "dialogo-error", text: error.message }));
      return;
    }

    const selector = el("select", { id: "dlgCarrito" });
    for (const c of carritos) {
      selector.append(el("option", { value: String(c.id), text: `${c.nombre || "Carrito " + c.id} · presupuesto ${pesos.format(c.presupuesto)}` }));
    }
    selector.append(el("option", { value: "nuevo", text: "+ Crear un carrito nuevo" }));
    if (carritos.length === 0) selector.value = "nuevo";

    const nombre = el("input", { type: "text", id: "dlgNombre", maxlength: "100", placeholder: "Nombre (opcional), por ejemplo «Mercado»" });
    const presupuesto = el("input", { type: "number", id: "dlgPresupuesto", min: "1", step: "1", placeholder: "Presupuesto del carrito ($)" });
    const sugerido = Number(document.querySelector("#budgetInput")?.value);
    if (sugerido > 0) presupuesto.value = String(sugerido);
    const cajaNuevo = el("div", { class: "dialogo-nuevo" }, el("label", { for: "dlgNombre", text: "Nombre del carrito" }), nombre,
      el("label", { for: "dlgPresupuesto", text: "Presupuesto" }), presupuesto);

    const prioridad = el("select", { id: "dlgPrioridad" });
    for (const [valor, texto] of PRIORIDADES) prioridad.append(el("option", { value: String(valor), text: texto }));
    prioridad.value = "3";

    const mensaje = el("p", { class: "dialogo-error", role: "status" });
    const guardar = el("button", { type: "button", class: "button button-primary", text: "Agregar" });
    const alternar = () => { cajaNuevo.hidden = selector.value !== "nuevo"; };
    selector.addEventListener("change", alternar);
    alternar();

    guardar.addEventListener("click", async () => {
      mensaje.textContent = "";
      guardar.disabled = true;
      try {
        let id = Number(selector.value);
        if (selector.value === "nuevo") {
          const valor = Number(presupuesto.value);
          if (!(valor > 0)) throw new Error("Escribe el presupuesto del carrito (un número mayor que cero).");
          id = (await PicksyAPI.crearCarrito(nombre.value.trim(), valor)).id;
        }
        await PicksyAPI.agregarAlCarrito(id, opcion, Number(prioridad.value));
        dialogo.close();
        aviso("Producto agregado al carrito. Míralo en «Mis carritos».");
      } catch (error) {
        mensaje.textContent = error.message || "No se pudo agregar el producto.";
        guardar.disabled = false;
      }
    });

    cuerpo.replaceChildren(
      el("label", { for: "dlgCarrito", text: "Carrito" }), selector, cajaNuevo,
      el("label", { for: "dlgPrioridad", text: "¿Qué tan importante es para ti?" }), prioridad,
      mensaje, guardar,
    );
  }

  // ---------- Variación de precios ----------
  function grafica(consultas) {
    const NS = "http://www.w3.org/2000/svg";
    const ancho = 420, alto = 140, margen = 12;
    const precios = consultas.map((c) => c.precio);
    const min = Math.min(...precios), max = Math.max(...precios);
    const rango = max - min || 1;
    const puntos = consultas.map((c, i) => {
      const x = margen + (consultas.length === 1 ? (ancho - 2 * margen) / 2 : (i * (ancho - 2 * margen)) / (consultas.length - 1));
      const y = alto - margen - ((c.precio - min) / rango) * (alto - 2 * margen);
      return [x, y];
    });
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
    svg.setAttribute("class", "grafica-precios");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Evolución del precio");
    const linea = document.createElementNS(NS, "polyline");
    linea.setAttribute("points", puntos.map((p) => p.join(",")).join(" "));
    linea.setAttribute("fill", "none");
    linea.setAttribute("stroke", "#263D2B");
    linea.setAttribute("stroke-width", "2.5");
    linea.setAttribute("stroke-linejoin", "round");
    svg.append(linea);
    for (const [x, y] of puntos) {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", "4"); c.setAttribute("fill", "#ECE99B"); c.setAttribute("stroke", "#263D2B"); c.setAttribute("stroke-width", "2");
      svg.append(c);
    }
    return svg;
  }

  async function mostrarVariacion(url, nombre) {
    const dialogo = crearDialogo("Precio en el tiempo");
    dialogo.append(el("p", { class: "muted", text: nombre || "" }));
    const cuerpo = el("div", { class: "dialogo-cuerpo" }, el("p", { class: "muted", text: "Consultando el historial..." }));
    dialogo.append(cuerpo);
    dialogo.showModal();
    try {
      const datos = await PicksyAPI.variacionDePrecio(url);
      const v = datos.variacion;
      const partes = [el("p", { class: "dialogo-precio", text: datos.mensaje })];
      if (datos.consultas.length > 0) partes.push(grafica(datos.consultas));
      const filas = [["Consultas guardadas", String(v.consultas)], ["Precio más bajo", pesos.format(v.minimo)], ["Precio más alto", pesos.format(v.maximo)]];
      if (v.cambio !== null && v.cambio !== undefined) {
        filas.push(["Cambio total", `${v.cambio > 0 ? "+" : ""}${pesos.format(v.cambio)}` + (v.cambio_porcentaje !== null ? ` (${v.cambio_porcentaje > 0 ? "+" : ""}${v.cambio_porcentaje} %)` : "")]);
      }
      const lista = el("dl", { class: "dialogo-datos" });
      for (const [k, val] of filas) lista.append(el("dt", { text: k }), el("dd", { text: val }));
      partes.push(lista);
      cuerpo.replaceChildren(...partes);
    } catch (error) {
      cuerpo.replaceChildren(el("p", { class: "dialogo-error", text: error.message || "No se pudo consultar el historial." }));
    }
  }

  window.PicksyUI = { elegirCarrito, mostrarVariacion, aviso, pesos };
})();
