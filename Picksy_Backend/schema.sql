-- =====================================================
-- SmartBudget · Esquema de base de datos (tarea B-01)
-- Ejecutar en pgAdmin sobre la base de datos "smartbudget"
-- =====================================================

-- 1. USUARIOS (RF-01 a RF-03)
CREATE TABLE IF NOT EXISTS usuarios (
    id              SERIAL PRIMARY KEY,
    correo          VARCHAR(255) NOT NULL UNIQUE,   -- UNIQUE: rechaza correos repetidos
    contrasena_hash VARCHAR(255) NOT NULL,          -- nunca se guarda la contraseña real
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. TIENDAS (las 10 del alcance)
CREATE TABLE IF NOT EXISTS tiendas (
    id         SERIAL PRIMARY KEY,
    nombre     VARCHAR(100) NOT NULL UNIQUE,
    sitio_web  VARCHAR(255) NOT NULL,
    activa     BOOLEAN NOT NULL DEFAULT TRUE
);

-- 3. PRODUCTOS (un producto tal como aparece en una tienda)
CREATE TABLE IF NOT EXISTS productos (
    id          SERIAL PRIMARY KEY,
    tienda_id   INTEGER NOT NULL REFERENCES tiendas(id),
    nombre      VARCHAR(500) NOT NULL,
    url         TEXT NOT NULL,                      -- enlace a la tienda original (RF-12)
    imagen_url  TEXT,
    categoria   VARCHAR(50),
    UNIQUE (tienda_id, url)
);

-- 4. PRECIOS (cada fila es una "foto" del precio en un momento)
--    Sirve para la caché (RF-05), la fecha de actualización (RNF-08)
--    y la variación de precios en el tiempo (RF-16)
CREATE TABLE IF NOT EXISTS precios (
    id            SERIAL PRIMARY KEY,
    producto_id   INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    precio        NUMERIC(12,2) NOT NULL CHECK (precio >= 0),
    envio         NUMERIC(12,2) CHECK (envio >= 0),  -- NULL = la tienda no lo informa
    disponible    BOOLEAN NOT NULL DEFAULT TRUE,    -- agotado = FALSE (A-05)
    consultado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_precios_producto_fecha
    ON precios (producto_id, consultado_en DESC);

-- 5. HISTORIAL DE BÚSQUEDAS (RF-15)
CREATE TABLE IF NOT EXISTS historial_busquedas (
    id           SERIAL PRIMARY KEY,
    usuario_id   INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    termino      VARCHAR(255) NOT NULL,
    presupuesto  NUMERIC(12,2) NOT NULL CHECK (presupuesto > 0),
    resultado    JSONB,                             -- resumen de lo que se mostró
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. CARRITOS (RF-13, RF-14, RF-17)
CREATE TABLE IF NOT EXISTS carritos (
    id           SERIAL PRIMARY KEY,
    usuario_id   INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre       VARCHAR(100),
    presupuesto  NUMERIC(12,2) NOT NULL CHECK (presupuesto > 0),
    total        NUMERIC(12,2) NOT NULL DEFAULT 0,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. ITEMS DEL CARRITO (productos con prioridad)
CREATE TABLE IF NOT EXISTS carrito_items (
    id               SERIAL PRIMARY KEY,
    carrito_id       INTEGER NOT NULL REFERENCES carritos(id) ON DELETE CASCADE,
    producto_id      INTEGER NOT NULL REFERENCES productos(id),
    prioridad        INTEGER NOT NULL CHECK (prioridad BETWEEN 1 AND 5),  -- A-03: 1 a 5
    precio_total     NUMERIC(12,2) NOT NULL,        -- precio + envío al momento de armar el carrito
    incluido         BOOLEAN NOT NULL DEFAULT FALSE -- TRUE si la mochila lo dejó dentro
);

-- 8. SESIONES (B-02: login, logout y expiración a 24 h, RF-02 y RF-03)
CREATE TABLE IF NOT EXISTS sesiones (
    token       VARCHAR(100) PRIMARY KEY,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creada_en   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_en   TIMESTAMPTZ NOT NULL
);

-- 9. CACHÉ DE BÚSQUEDAS (RF-05: no volver a consultar las tiendas durante 24 h)
CREATE TABLE IF NOT EXISTS cache_busquedas (
    id             SERIAL PRIMARY KEY,
    termino        VARCHAR(100) NOT NULL,
    tienda_id      INTEGER NOT NULL REFERENCES tiendas(id),
    consultado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (termino, tienda_id)
);

-- 10. QUÉ PRODUCTOS DEVOLVIÓ CADA BÚSQUEDA GUARDADA
CREATE TABLE IF NOT EXISTS cache_resultados (
    cache_id     INTEGER NOT NULL REFERENCES cache_busquedas(id) ON DELETE CASCADE,
    producto_id  INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    PRIMARY KEY (cache_id, producto_id)
);

-- =====================================================
-- DATOS INICIALES: las 10 tiendas
-- =====================================================
INSERT INTO tiendas (nombre, sitio_web) VALUES
    ('Mercado Libre', 'https://www.mercadolibre.com.co'),
    ('Alkosto',       'https://www.alkosto.com'),
    ('Homecenter',    'https://www.homecenter.com.co'),
    ('Éxito',         'https://www.exito.com'),
    ('Falabella',     'https://www.falabella.com.co'),
    ('Ktronix',       'https://www.ktronix.com'),
    ('Farmatodo',     'https://www.farmatodo.com.co'),
    ('Alkomprar',     'https://www.alkomprar.com'),
    ('Olímpica',      'https://www.olimpica.com'),
    ('Buscalibre',    'https://www.buscalibre.com.co')
ON CONFLICT (nombre) DO NOTHING;