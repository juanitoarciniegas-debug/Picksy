
document.addEventListener("DOMContentLoaded", () => {
    const registerForm = document.getElementById("registerForm");

    if (!registerForm) {
        console.error("No se encontró el formulario de registro.");
        return;
    }

    const username = document.getElementById("username");
    const email = document.getElementById("registerEmail");
    const password = document.getElementById("registerPassword");
    const confirmPassword = document.getElementById("confirmPassword");
    const acceptTerms = document.getElementById("acceptTerms");

    const nameError = document.getElementById("nameError");
    const emailError = document.getElementById("registerEmailError");
    const passwordError = document.getElementById("registerPasswordError");
    const confirmPasswordError = document.getElementById("confirmPasswordError");
    const feedback = document.getElementById("registerFeedback");

    // CAMBIO (backend): botón de envío, para bloquearlo mientras se espera la respuesta del servidor.
    const botonEnviar = registerForm.querySelector('button[type="submit"]');

    // Escucha el envío del formulario.
    registerForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        limpiarErrores();

        const nombre = username.value.trim();
        const correo = email.value.trim();
        const clave = password.value;
        const confirmarClave = confirmPassword.value;

        let formularioValido = true;

        // Validar nombre.
        if (nombre.length < 2) {
            mostrarError(nameError, "Ingresa un nombre de al menos 2 caracteres.");
            formularioValido = false;
        }

        // Validar correo.
        if (!validarCorreo(correo)) {
            mostrarError(emailError, "Ingresa un correo electrónico válido.");
            formularioValido = false;
        }

        // Validar contraseña.
        if (clave.length < 8) {
            mostrarError(passwordError, "La contraseña debe tener al menos 8 caracteres.");
            formularioValido = false;
        } else if (clave.length > 50) {
            // CAMBIO (backend): el backend rechaza contraseñas de más de 50 caracteres.
            mostrarError(passwordError, "La contraseña no puede tener más de 50 caracteres.");
            formularioValido = false;
        }

        // Confirmar contraseña.
        if (clave !== confirmarClave) {
            mostrarError(confirmPasswordError, "Las contraseñas no coinciden.");
            formularioValido = false;
        }

        // Aceptación de términos.
        if (!acceptTerms.checked) {
            mostrarFeedback("Debes aceptar los términos y condiciones.", "error");
            formularioValido = false;
        }

        if (!formularioValido) {
            return;
        }

        // Datos que posteriormente enviaremos al backend.
        const usuario = {
            nombre: nombre,
            correo: correo,
            password: clave
        };

        try {
            mostrarFeedback("Validando información...", "info");

            // CAMBIO (backend): se bloquea el botón para evitar enviar el formulario dos veces.
            if (botonEnviar) botonEnviar.disabled = true;

            // Preparada para conectar con el servicio de registro.
            // (Ya conectada: ver la función registrarUsuario más abajo.)
            const resultado = await registrarUsuario(usuario);

            if (resultado.success) {
                mostrarFeedback(
                    "¡Registro completado correctamente!",
                    "success"
                );

                registerForm.reset();

                // Cuando exista el backend, aquí podremos redirigir
                // al usuario o iniciar su sesión.
                // CAMBIO (backend): el backend ya existe; se redirige al login a los 1.5 segundos.
                setTimeout(() => {
                    window.location.href = "login.html";
                }, 1500);
            } else {
                mostrarFeedback(
                    resultado.message || "No fue posible completar el registro.",
                    "error"
                );
            }
        } catch (error) {
            console.error("Error durante el registro:", error);

            mostrarFeedback(
                "Ocurrió un error. Inténtalo de nuevo más tarde.",
                "error"
            );
        } finally {
            // CAMBIO (backend): se vuelve a habilitar el botón, haya salido bien o mal.
            if (botonEnviar) botonEnviar.disabled = false;
        }
    });

    // Comprueba el formato básico del correo electrónico.
    function validarCorreo(correo) {
        const expresion = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return expresion.test(correo);
    }

    // Muestra un error junto al campo correspondiente.

    function mostrarError(elemento, mensaje) {
        if (!elemento) return;

        elemento.textContent = mensaje;

        const campoId = {
            nameError: "username",
            registerEmailError: "registerEmail",
            registerPasswordError: "registerPassword",
            confirmPasswordError: "confirmPassword"
        };

        const campo = document.getElementById(campoId[elemento.id]);

        if (campo) {
            campo.classList.add("invalid");
        }
    }

    // Limpia los errores anteriores.
    // CAMBIO (backend): esta función estaba definida dos veces en el archivo; la segunda
    // anulaba a la primera y no quitaba la marca roja ("invalid") de los campos.
    // Se dejó una sola, que limpia los textos de error, la marca roja y el mensaje general.
    function limpiarErrores() {
        [
            nameError,
            emailError,
            passwordError,
            confirmPasswordError
        ].forEach((elemento) => {
            if (elemento) {
                elemento.textContent = "";
            }
        });

        [
            username,
            email,
            password,
            confirmPassword
        ].forEach((campo) => {
            if (campo) {
                campo.classList.remove("invalid");
            }
        });

        if (feedback) {
            feedback.textContent = "";
            feedback.className = "register-feedback";
        }
    }

    // Muestra mensajes generales del formulario.
    function mostrarFeedback(mensaje, tipo) {
        if (!feedback) return;

        feedback.textContent = mensaje;
        feedback.className = `register-feedback ${tipo}`;
    }

    /**
     * FUNCIÓN CONECTADA AL BACKEND
     *
     * Antes: "Actualmente no crea usuarios ni guarda información.
     * Cuando el backend esté disponible, aquí conectaremos
     * el formulario con su API."
     *
     * CAMBIO (backend): ahora llama a PicksyAPI.registrar (definida en js/api.js), que envía
     * los datos a POST /auth/registro del backend y devuelve { success, message }.
     * Requiere que js/api.js esté cargado en registro.html ANTES de este archivo.
     */
    async function registrarUsuario(usuario) {
        console.log("Datos preparados para el registro:", {
            nombre: usuario.nombre,
            correo: usuario.correo
        });

        // Ejemplo futuro de conexión (REEMPLAZADO por PicksyAPI.registrar, que usa la ruta real
        // "/auth/registro" y el campo "contrasena" en lugar de "password"):
        //
        // const respuesta = await fetch("URL_DEL_BACKEND/registro", {
        //     method: "POST",
        //     headers: {
        //         "Content-Type": "application/json"
        //     },
        //     body: JSON.stringify(usuario)
        // });
        //
        // const resultado = await respuesta.json();
        //
        // if (!respuesta.ok) {
        //     throw new Error(resultado.message || "Error de registro");
        // }
        //
        // return resultado;

        // CAMBIO (backend): si falta cargar js/api.js, se avisa con un mensaje claro.
        if (typeof PicksyAPI === "undefined") {
            return {
                success: false,
                message: "Falta cargar js/api.js en registro.html."
            };
        }

        // Comportamiento anterior (provisional): no registraba usuarios reales.
        // Ahora sí se crea el usuario en la base de datos del backend.
        try {
            await PicksyAPI.registrar({
                nombre: usuario.nombre,
                correo: usuario.correo,
                contrasena: usuario.password // el backend espera "contrasena", no "password"
            });
            return { success: true };
        } catch (error) {
            return { success: false, message: error.message };
        }
    }
});
