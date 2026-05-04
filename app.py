from flask import Flask, render_template, request, redirect, send_file, session, jsonify, flash, url_for
import os
import hashlib
from datetime import datetime, date, timedelta
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib.parse

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "granja_segura_2024_v2")
app.config['JSON_AS_ASCII'] = False

# ========== CONFIGURACIÓN POSTGRESQL ==========
def get_db():
    """Conexión a PostgreSQL usando DATABASE_URL de Render"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # Fallback para desarrollo local
        database_url = "postgresql://granja_user:granja_pass@localhost:5432/granja_db"

    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('rol') != 'admin':
            flash("No tienes permisos para acceder a esta sección", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def operario_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('rol') not in ('admin', 'operario'):
            flash("No tienes permisos", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def init_db():
    conn = get_db()
    c = conn.cursor()

    # USUARIOS
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        nombre TEXT NOT NULL,
        rol TEXT NOT NULL DEFAULT 'operario' CHECK(rol IN ('admin', 'operario')),
        activo INTEGER DEFAULT 1
    )''')

    # TABLAS PRINCIPALES
    c.execute('''CREATE TABLE IF NOT EXISTS gallinas (
        id SERIAL PRIMARY KEY,
        fecha DATE NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('ingreso', 'muerte', 'venta')),
        cantidad INTEGER NOT NULL,
        notas TEXT,
        usuario_id INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS huevos (
        id SERIAL PRIMARY KEY,
        fecha DATE NOT NULL,
        cantidad INTEGER NOT NULL,
        calidad TEXT DEFAULT 'A',
        notas TEXT,
        usuario_id INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS alimento (
        id SERIAL PRIMARY KEY,
        fecha DATE NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('gallinas', 'pollos')),
        cantidad_kg REAL NOT NULL,
        costo REAL NOT NULL,
        proveedor TEXT,
        notas TEXT,
        usuario_id INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        telefono TEXT,
        email TEXT,
        direccion TEXT,
        fecha_registro DATE DEFAULT CURRENT_DATE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS productos (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        tipo TEXT NOT NULL,
        unidad TEXT DEFAULT 'unidad'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS ventas (
        id SERIAL PRIMARY KEY,
        fecha DATE NOT NULL,
        producto_id INTEGER NOT NULL,
        cliente_id INTEGER,
        cantidad REAL NOT NULL,
        precio_unitario REAL NOT NULL,
        total REAL NOT NULL,
        estado TEXT DEFAULT 'ACTIVA' CHECK(estado IN ('ACTIVA', 'ANULADA')),
        estado_pago TEXT DEFAULT 'PENDIENTE' CHECK(estado_pago IN ('PENDIENTE', 'PARCIAL', 'PAGADO')),
        abono REAL DEFAULT 0,
        monto_pagado REAL DEFAULT 0,
        fecha_pago DATE,
        factura_numero TEXT,
        usuario_id INTEGER,
        FOREIGN KEY (producto_id) REFERENCES productos(id),
        FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS costos (
        id SERIAL PRIMARY KEY,
        fecha DATE NOT NULL,
        categoria TEXT NOT NULL CHECK(categoria IN ('alimento', 'medicina', 'empaque', 'mano_obra', 'transporte', 'pollitos', 'otros')),
        descripcion TEXT NOT NULL,
        valor REAL NOT NULL,
        producto_relacionado TEXT DEFAULT 'general' CHECK(producto_relacionado IN ('huevos', 'pollos', 'general'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS pollos_crianza (
        id SERIAL PRIMARY KEY,
        lote TEXT UNIQUE NOT NULL,
        fecha_ingreso DATE NOT NULL,
        cantidad_inicial INTEGER NOT NULL,
        cantidad_actual INTEGER NOT NULL,
        peso_inicial REAL NOT NULL,
        costo_pollitos REAL DEFAULT 0,
        estado TEXT DEFAULT 'ACTIVO' CHECK(estado IN ('ACTIVO', 'FINALIZADO'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS control_peso (
        id SERIAL PRIMARY KEY,
        crianza_id INTEGER NOT NULL,
        fecha DATE NOT NULL,
        semana INTEGER NOT NULL,
        peso_promedio REAL NOT NULL,
        cantidad_viva INTEGER NOT NULL,
        alimento_consumido_kg REAL DEFAULT 0,
        mortalidad INTEGER DEFAULT 0,
        usuario_id INTEGER,
        FOREIGN KEY (crianza_id) REFERENCES pollos_crianza(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS costos_preparacion (
        id SERIAL PRIMARY KEY,
        crianza_id INTEGER NOT NULL,
        fecha DATE NOT NULL,
        descripcion TEXT NOT NULL,
        valor REAL NOT NULL,
        FOREIGN KEY (crianza_id) REFERENCES pollos_crianza(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS pollos_listos (
        id SERIAL PRIMARY KEY,
        crianza_id INTEGER NOT NULL,
        fecha_listo DATE NOT NULL,
        cantidad INTEGER NOT NULL,
        peso_promedio REAL NOT NULL,
        costo_total REAL DEFAULT 0,
        precio_venta_unitario REAL DEFAULT 0,
        estado TEXT DEFAULT 'DISPONIBLE' CHECK(estado IN ('DISPONIBLE', 'VENDIDO')),
        FOREIGN KEY (crianza_id) REFERENCES pollos_crianza(id)
    )''')

    # DATOS BASE
    c.execute("SELECT COUNT(*) FROM productos")
    existe = c.fetchone()['count']
    if existe == 0:
        c.execute("INSERT INTO productos (nombre, tipo, unidad) VALUES (%s,%s,%s)",
                  ('Huevos', 'huevo', 'unidad'))
        c.execute("INSERT INTO productos (nombre, tipo, unidad) VALUES (%s,%s,%s)",
                  ('Pollos de Engorde', 'pollo', 'unidad'))
        c.execute("INSERT INTO productos (nombre, tipo, unidad) VALUES (%s,%s,%s)",
                  ('Pollo por Libra', 'pollo_libra', 'libra'))

    # USUARIOS BASE
    c.execute("SELECT COUNT(*) FROM usuarios")
    existe_u = c.fetchone()['count']
    if existe_u == 0:
        c.execute("INSERT INTO usuarios (username, password, nombre, rol) VALUES (%s,%s,%s,%s)",
                  ("admin", hash_password("1234"), "Administrador", "admin"))
        c.execute("INSERT INTO usuarios (username, password, nombre, rol) VALUES (%s,%s,%s,%s)",
                  ("operario", hash_password("1234"), "Operario de Granja", "operario"))

    conn.commit()
    conn.close()

init_db()

# ========================
# UTILIDADES
# ========================

def get_factura_numero():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM ventas WHERE estado='ACTIVA'")
    count = c.fetchone()['count'] + 1
    conn.close()
    return f"F-{datetime.now().strftime('%Y%m')}-{str(count).zfill(4)}"

def get_gallinas_total():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT SUM(CASE 
            WHEN tipo='ingreso' THEN cantidad 
            WHEN tipo IN ('muerte', 'venta') THEN -cantidad 
        END) as total
        FROM gallinas
    """)
    result = c.fetchone()
    total = result['total'] if result and result['total'] else 0
    conn.close()
    return total

def get_huevos_disponibles():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(cantidad) as total FROM huevos")
    result = c.fetchone()
    producidos = result['total'] if result and result['total'] else 0
    c.execute("SELECT SUM(cantidad) as total FROM ventas WHERE producto_id=1 AND estado='ACTIVA'")
    result = c.fetchone()
    vendidos = result['total'] if result and result['total'] else 0
    conn.close()
    return producidos - vendidos

def get_pollos_disponibles():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(cantidad) as total FROM pollos_listos WHERE estado='DISPONIBLE'")
    result = c.fetchone()
    listos = result['total'] if result and result['total'] else 0
    c.execute("SELECT SUM(cantidad) as total FROM ventas WHERE producto_id=2 AND estado='ACTIVA'")
    result = c.fetchone()
    vendidos = result['total'] if result and result['total'] else 0
    conn.close()
    return listos - vendidos

def get_costos_total(tipo=None):
    conn = get_db()
    c = conn.cursor()
    if tipo:
        c.execute("SELECT SUM(valor) as total FROM costos WHERE producto_relacionado=%s", (tipo,))
    else:
        c.execute("SELECT SUM(valor) as total FROM costos")
    result = c.fetchone()
    total = result['total'] if result and result['total'] else 0
    conn.close()
    return total

def get_ventas_total():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(total) as total FROM ventas WHERE estado='ACTIVA'")
    result = c.fetchone()
    total = result['total'] if result and result['total'] else 0
    conn.close()
    return total

def get_user_id():
    return session.get('user_id')

# ========================
# AUTH
# ========================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('user', '')
        password = request.form.get('password', '')
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE username=%s AND password=%s AND activo=1",
                    (user, hash_password(password)))
        row = c.fetchone()
        conn.close()
        if row:
            session['user_id'] = row['id']
            session['username'] = row['username']
            session['nombre'] = row['nombre']
            session['rol'] = row['rol']
            flash(f"Bienvenido {row['nombre']}", "success")
            return redirect(url_for('index'))
        else:
            flash("Usuario o contraseña incorrectos", "danger")
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada", "info")
    return redirect(url_for('login'))

# ========================
# DASHBOARD
# ========================

@app.route('/')
@login_required
def index():
    conn = get_db()
    c = conn.cursor()

    gallinas = get_gallinas_total()
    huevos = get_huevos_disponibles()
    pollos = get_pollos_disponibles()
    ventas_total = get_ventas_total()
    costos_total = get_costos_total()
    ganancia = ventas_total - costos_total

    alertas = []
    if huevos < 50:
        alertas.append({"tipo": "warning", "msg": f"⚠️ Pocos huevos disponibles ({huevos} unidades)"})
    if pollos < 10:
        alertas.append({"tipo": "warning", "msg": f"⚠️ Pocos pollos en inventario ({pollos} unidades)"})
    if gallinas < 20:
        alertas.append({"tipo": "danger", "msg": f"🚨 Gallinas por debajo del mínimo ({gallinas})"})
    if ganancia < 0 and session.get('rol') == 'admin':
        alertas.append({"tipo": "danger", "msg": f"📉 Pérdidas detectadas: ${ganancia:,.2f}"})

    c.execute("""
        SELECT TO_CHAR(fecha, 'YYYY-MM') as mes, SUM(total) as total 
        FROM ventas WHERE estado='ACTIVA' 
        GROUP BY mes ORDER BY mes DESC LIMIT 6
    """)
    ventas_mes = c.fetchall()

    c.execute("""
        SELECT TO_CHAR(fecha, 'YYYY-MM') as mes, SUM(cantidad) as total 
        FROM huevos 
        GROUP BY mes ORDER BY mes DESC LIMIT 6
    """)
    huevos_mes = c.fetchall()

    c.execute("SELECT * FROM pollos_crianza WHERE estado='ACTIVO' ORDER BY fecha_ingreso DESC")
    crianzas = c.fetchall()

    conn.close()

    return render_template("index.html",
                           gallinas=gallinas,
                           huevos=huevos,
                           pollos=pollos,
                           ventas_total=ventas_total,
                           costos_total=costos_total,
                           ganancia=ganancia,
                           alertas=alertas,
                           ventas_mes=ventas_mes,
                           huevos_mes=huevos_mes,
                           crianzas=crianzas)

# ========================
# GALLINAS
# ========================

@app.route('/gallinas', methods=['GET', 'POST'])
@admin_required
def gallinas():
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        try:
            c.execute("""
                INSERT INTO gallinas (fecha, tipo, cantidad, notas, usuario_id) 
                VALUES (%s,%s,%s,%s,%s)
            """, (
                request.form.get('fecha', date.today().isoformat()),
                request.form['tipo'],
                int(request.form['cantidad']),
                request.form.get('notas', ''),
                get_user_id()
            ))
            conn.commit()
            flash("Registro guardado", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('gallinas'))

    c.execute("SELECT g.*, u.nombre as usuario FROM gallinas g LEFT JOIN usuarios u ON g.usuario_id=u.id ORDER BY fecha DESC")
    data = c.fetchall()
    total = get_gallinas_total()
    conn.close()
    return render_template("gallinas.html", data=data, total=total)

@app.route('/gallinas/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar_gallina(id):
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        c.execute("""UPDATE gallinas SET fecha=%s, tipo=%s, cantidad=%s, notas=%s WHERE id=%s""",
                  (request.form['fecha'], request.form['tipo'], int(request.form['cantidad']),
                   request.form.get('notas', ''), id))
        conn.commit()
        flash("Registro actualizado", "success")
        return redirect(url_for('gallinas'))
    c.execute("SELECT * FROM gallinas WHERE id=%s", (id,))
    data = c.fetchone()
    conn.close()
    return render_template("editar_gallina.html", d=data)

@app.route('/gallinas/eliminar/<int:id>')
@admin_required
def eliminar_gallina(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM gallinas WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Registro eliminado", "info")
    return redirect(url_for('gallinas'))

# ========================
# ALIMENTO
# ========================

@app.route('/alimento', methods=['GET', 'POST'])
@admin_required
def alimento():
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        try:
            c.execute("""
                INSERT INTO alimento (fecha, tipo, cantidad_kg, costo, proveedor, notas, usuario_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                request.form.get('fecha', date.today().isoformat()),
                request.form['tipo'],
                float(request.form['cantidad_kg']),
                float(request.form['costo']),
                request.form.get('proveedor', ''),
                request.form.get('notas', ''),
                get_user_id()
            ))
            conn.commit()
            flash("Compra registrada", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('alimento'))

    c.execute("SELECT a.*, u.nombre as usuario FROM alimento a LEFT JOIN usuarios u ON a.usuario_id=u.id ORDER BY fecha DESC")
    data = c.fetchall()
    c.execute("""
        SELECT TO_CHAR(fecha, 'YYYY-MM') as mes, SUM(costo) as total
        FROM alimento GROUP BY mes ORDER BY mes DESC LIMIT 12
    """)
    gasto_mes = c.fetchall()
    conn.close()
    return render_template("alimento.html", data=data, gasto_mes=gasto_mes)

@app.route('/alimento/eliminar/<int:id>')
@admin_required
def eliminar_alimento(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM alimento WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Registro eliminado", "info")
    return redirect(url_for('alimento'))

# ========================
# HUEVOS (ADMIN + OPERARIO)
# ========================

@app.route('/huevos', methods=['GET', 'POST'])
@operario_required
def huevos():
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        try:
            c.execute("""
                INSERT INTO huevos (fecha, cantidad, calidad, notas, usuario_id)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                request.form.get('fecha', date.today().isoformat()),
                int(request.form['cantidad']),
                request.form.get('calidad', 'A'),
                request.form.get('notas', ''),
                get_user_id()
            ))
            conn.commit()
            flash("Recolección registrada", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('huevos'))

    c.execute("""
        SELECT h.*, u.nombre as usuario 
        FROM huevos h 
        LEFT JOIN usuarios u ON h.usuario_id=u.id 
        ORDER BY fecha DESC
    """)
    data = c.fetchall()
    total_disponible = get_huevos_disponibles()
    c.execute("""
        SELECT TO_CHAR(fecha, 'YYYY-MM') as mes, SUM(cantidad) as total
        FROM huevos GROUP BY mes ORDER BY mes DESC LIMIT 12
    """)
    prod_mes = c.fetchall()
    conn.close()
    return render_template("huevos.html", data=data, total=total_disponible, prod_mes=prod_mes)

@app.route('/huevos/eliminar/<int:id>')
@admin_required
def eliminar_huevo(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM huevos WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Registro eliminado", "info")
    return redirect(url_for('huevos'))

# ========================
# CLIENTES
# ========================

@app.route('/clientes', methods=['GET', 'POST'])
@admin_required
def clientes():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        try:
            c.execute("""
                INSERT INTO clientes (nombre, telefono, email, direccion)
                VALUES (%s,%s,%s,%s)
            """, (request.form['nombre'], request.form.get('telefono', ''),
                  request.form.get('email', ''), request.form.get('direccion', '')))
            conn.commit()
            flash("Cliente registrado", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('clientes'))
    c.execute("SELECT * FROM clientes ORDER BY nombre")
    data = c.fetchall()
    conn.close()
    return render_template("clientes.html", data=data)

@app.route('/clientes/eliminar/<int:id>')
@admin_required
def eliminar_cliente(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM clientes WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Cliente eliminado", "info")
    return redirect(url_for('clientes'))

# ========================
# VENTAS
# ========================

@app.route('/ventas', methods=['GET', 'POST'])
@admin_required
def ventas():
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        try:
            producto_id = int(request.form['producto'])
            cantidad = float(request.form['cantidad'])
            precio = float(request.form['precio'])
            total = cantidad * precio

            if producto_id == 1:
                disponible = get_huevos_disponibles()
                if cantidad > disponible:
                    flash(f"Stock insuficiente. Disponible: {disponible}", "danger")
                    return redirect(url_for('ventas'))
            elif producto_id == 2:
                disponible = get_pollos_disponibles()
                if cantidad > disponible:
                    flash(f"Stock insuficiente. Disponible: {disponible}", "danger")
                    return redirect(url_for('ventas'))

            factura = get_factura_numero()
            c.execute("""
                INSERT INTO ventas (fecha, producto_id, cliente_id, cantidad, precio_unitario, total, estado_pago, fecha_pago, factura_numero, usuario_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                request.form.get('fecha', date.today().isoformat()),
                producto_id, request.form.get('cliente') or None,
                cantidad, precio, total,
                request.form.get('estado_pago', 'PENDIENTE'),
                request.form.get('fecha_pago', '') or None,
                factura, get_user_id()
            ))
            conn.commit()
            flash(f"Venta registrada. Factura: {factura}", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('ventas'))

    c.execute("SELECT * FROM productos")
    productos = c.fetchall()
    c.execute("SELECT * FROM clientes ORDER BY nombre")
    clientes_list = c.fetchall()
    c.execute("""
        SELECT v.*, p.nombre as producto, p.unidad, c.nombre as cliente
        FROM ventas v JOIN productos p ON v.producto_id = p.id
        LEFT JOIN clientes c ON v.cliente_id = c.id ORDER BY v.id DESC
    """)
    data = c.fetchall()
    # Ventas pendientes de pago
    c.execute("""
        SELECT v.*, p.nombre as producto, c.nombre as cliente
        FROM ventas v JOIN productos p ON v.producto_id = p.id
        LEFT JOIN clientes c ON v.cliente_id = c.id
        WHERE v.estado='ACTIVA' AND v.estado_pago IN ('PENDIENTE', 'PARCIAL')
        ORDER BY v.fecha DESC
    """)
    ventas_pendientes = c.fetchall()
    conn.close()
    return render_template("ventas.html", data=data, productos=productos, clientes=clientes_list, pendientes=ventas_pendientes)

@app.route('/ventas/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar_venta(id):
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        cantidad = float(request.form['cantidad'])
        precio = float(request.form['precio'])
        total = cantidad * precio
        c.execute("""UPDATE ventas SET fecha=%s, producto_id=%s, cliente_id=%s, cantidad=%s, 
                    precio_unitario=%s, total=%s WHERE id=%s""",
                  (request.form['fecha'], request.form['producto'],
                   request.form.get('cliente') or None, cantidad, precio, total, id))
        conn.commit()
        flash("Venta actualizada", "success")
        return redirect(url_for('ventas'))
    c.execute("SELECT * FROM ventas WHERE id=%s", (id,))
    venta = c.fetchone()
    c.execute("SELECT * FROM productos")
    productos = c.fetchall()
    c.execute("SELECT * FROM clientes ORDER BY nombre")
    clientes_list = c.fetchall()
    conn.close()
    return render_template("editar_venta.html", venta=venta, productos=productos, clientes=clientes_list)

@app.route('/ventas/anular/<int:id>')
@admin_required
def anular_venta(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE ventas SET estado='ANULADA' WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Venta anulada", "warning")
    return redirect(url_for('ventas'))

@app.route('/ventas/pagar/<int:id>', methods=['GET', 'POST'])
@admin_required
def registrar_pago(id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM ventas WHERE id=%s", (id,))
    venta = c.fetchone()
    if not venta:
        flash("Venta no encontrada", "danger")
        return redirect(url_for('ventas'))

    if request.method == 'POST':
        try:
            monto = float(request.form['monto'])
            fecha_pago = request.form.get('fecha_pago', date.today().isoformat())

            nuevo_abono = (venta['abono'] or 0) + monto
            nuevo_saldo = venta['total'] - nuevo_abono

            if nuevo_saldo <= 0:
                estado_pago = 'PAGADO'
                nuevo_abono = venta['total']
            else:
                estado_pago = 'PARCIAL'

            c.execute('''UPDATE ventas SET abono=%s, estado_pago=%s, fecha_pago=%s WHERE id=%s''',
                      (nuevo_abono, estado_pago, fecha_pago, id))
            conn.commit()
            flash(f"Pago registrado: ${monto:,.2f}. Saldo restante: ${nuevo_saldo:,.2f}", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('ventas'))

    conn.close()
    return render_template("registrar_pago.html", venta=venta)

@app.route('/ventas/marcar_pagado/<int:id>')
@admin_required
def marcar_pagado(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE ventas SET estado_pago='PAGADO', fecha_pago=%s WHERE id=%s", 
              (date.today().isoformat(), id))
    conn.commit()
    conn.close()
    flash("Venta marcada como PAGADA", "success")
    return redirect(url_for('ventas'))

@app.route('/ventas/pago/<int:id>', methods=['GET', 'POST'])
@admin_required
def actualizar_pago(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM ventas WHERE id=%s", (id,))
    venta = c.fetchone()

    if request.method == 'POST':
        try:
            estado_pago = request.form['estado_pago']
            monto_pagado = float(request.form.get('monto_pagado', 0))
            fecha_pago = request.form.get('fecha_pago')

            if estado_pago == 'PAGADO':
                monto_pagado = venta['total']
                if not fecha_pago:
                    fecha_pago = date.today().isoformat()
            elif estado_pago == 'PENDIENTE':
                monto_pagado = 0
                fecha_pago = None

            c.execute('''UPDATE ventas SET estado_pago=%s, monto_pagado=%s, fecha_pago=%s WHERE id=%s''',
                      (estado_pago, monto_pagado, fecha_pago, id))
            conn.commit()
            flash(f"Estado de pago actualizado a: {estado_pago}", "success")
            return redirect(url_for('ventas'))
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    conn.close()
    return render_template("actualizar_pago.html", venta=venta)

# ========================
# FACTURA
# ========================

@app.route('/factura/<int:id>')
@admin_required
def factura(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT v.*, p.nombre as producto, p.unidad, c.nombre as cliente, 
               c.telefono, c.direccion
        FROM ventas v JOIN productos p ON v.producto_id = p.id
        LEFT JOIN clientes c ON v.cliente_id = c.id WHERE v.id=%s
    """, (id,))
    venta = c.fetchone()
    conn.close()
    if not venta:
        return "Venta no encontrada", 404

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=30)
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24,
                                  textColor=colors.HexColor('#2c5530'), spaceAfter=30, alignment=1)
    contenido = []
    contenido.append(Paragraph("<b>GRANJA AVÍCOLA</b>", style_title))
    contenido.append(Paragraph("Sistema de Gestión Integral", styles['Normal']))
    contenido.append(Spacer(1, 20))
    contenido.append(Paragraph("<b>FACTURA DE VENTA</b>", styles['Heading2']))
    contenido.append(Paragraph(f"N°: <b>{venta['factura_numero']}</b>", styles['Normal']))
    contenido.append(Paragraph(f"Fecha: {venta['fecha']}", styles['Normal']))
    contenido.append(Spacer(1, 20))
    contenido.append(Paragraph(f"<b>CLIENTE:</b> {venta['cliente'] or 'Consumidor Final'}", styles['Normal']))
    if venta['telefono']:
        contenido.append(Paragraph(f"Teléfono: {venta['telefono']}", styles['Normal']))
    if venta['direccion']:
        contenido.append(Paragraph(f"Dirección: {venta['direccion']}", styles['Normal']))
    contenido.append(Spacer(1, 20))
    data_table = [['Producto', 'Cantidad', 'Precio Unit.', 'Total'],
                  [venta['producto'], f"{venta['cantidad']} {venta['unidad']}",
                   f"${venta['precio_unitario']:,.2f}", f"${venta['total']:,.2f}"]]
    tabla = Table(data_table, colWidths=[200, 100, 100, 100])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5530')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    contenido.append(tabla)
    contenido.append(Spacer(1, 30))
    contenido.append(Paragraph(f"<b>TOTAL A PAGAR: ${venta['total']:,.2f}</b>",
                               ParagraphStyle('Total', parent=styles['Heading2'], alignment=2, textColor=colors.HexColor('#2c5530'))))
    contenido.append(Spacer(1, 50))
    contenido.append(Paragraph("_" * 30, ParagraphStyle('Firma', alignment=1)))
    contenido.append(Paragraph("Firma y Sello", ParagraphStyle('Firma2', alignment=1)))
    doc.build(contenido)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"factura_{venta['factura_numero']}.pdf", mimetype='application/pdf')

# ========================
# POLLOS - CRIANZA (ADMIN + OPERARIO puede ver, ADMIN crea)
# ========================

@app.route('/pollos/crianza', methods=['GET', 'POST'])
@admin_required
def pollos_crianza():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        try:
            lote = request.form['lote']
            cantidad = int(request.form['cantidad'])
            c.execute("""
                INSERT INTO pollos_crianza (lote, fecha_ingreso, cantidad_inicial, cantidad_actual, peso_inicial, costo_pollitos)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (lote, request.form.get('fecha', date.today().isoformat()), cantidad, cantidad,
                  float(request.form['peso']), float(request.form.get('costo', 0))))
            conn.commit()
            flash("Lote registrado", "success")
        except psycopg2.IntegrityError:
            flash("El lote ya existe", "danger")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('pollos_crianza'))

    c.execute("SELECT * FROM pollos_crianza ORDER BY fecha_ingreso DESC")
    data = c.fetchall()
    conn.close()
    return render_template("pollos_crianza.html", data=data)

@app.route('/pollos/crianza/eliminar/<int:id>')
@admin_required
def eliminar_crianza(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM pollos_crianza WHERE id=%s", (id,))
    c.execute("DELETE FROM control_peso WHERE crianza_id=%s", (id,))
    c.execute("DELETE FROM costos_preparacion WHERE crianza_id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Lote eliminado", "info")
    return redirect(url_for('pollos_crianza'))

# ========================
# CONTROL DE PESO (ADMIN + OPERARIO)
# ========================

@app.route('/pollos/control/<int:crianza_id>', methods=['GET', 'POST'])
@operario_required
def control_peso(crianza_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM pollos_crianza WHERE id=%s", (crianza_id,))
    crianza = c.fetchone()
    if not crianza:
        flash("Lote no encontrado", "danger")
        return redirect(url_for('pollos_crianza'))

    if request.method == 'POST':
        try:
            semana = int(request.form['semana'])
            cantidad_viva = int(request.form['cantidad_viva'])
            mortalidad = crianza['cantidad_actual'] - cantidad_viva
            c.execute("""
                INSERT INTO control_peso (crianza_id, fecha, semana, peso_promedio, cantidad_viva, alimento_consumido_kg, mortalidad, usuario_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (crianza_id, request.form.get('fecha', date.today().isoformat()), semana,
                  float(request.form['peso']), cantidad_viva,
                  float(request.form.get('alimento', 0)),
                  mortalidad if mortalidad > 0 else 0, get_user_id()))
            c.execute("UPDATE pollos_crianza SET cantidad_actual=%s WHERE id=%s", (cantidad_viva, crianza_id))
            conn.commit()
            flash(f"Control semana {semana} registrado. Mortalidad: {mortalidad}", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('control_peso', crianza_id=crianza_id))

    c.execute("""
        SELECT cp.*, u.nombre as usuario 
        FROM control_peso cp 
        LEFT JOIN usuarios u ON cp.usuario_id=u.id 
        WHERE cp.crianza_id=%s ORDER BY semana
    """, (crianza_id,))
    data = c.fetchall()
    conn.close()
    return render_template("control_peso.html", data=data, crianza=crianza, crianza_id=crianza_id)

@app.route('/pollos/control/eliminar/<int:id>')
@admin_required
def eliminar_control(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT crianza_id FROM control_peso WHERE id=%s", (id,))
    row = c.fetchone()
    crianza_id = row['crianza_id'] if row else 0
    c.execute("DELETE FROM control_peso WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Registro eliminado", "info")
    return redirect(url_for('control_peso', crianza_id=crianza_id))

# ========================
# COSTOS DE PREPARACIÓN
# ========================

@app.route('/pollos/preparacion/<int:crianza_id>', methods=['GET', 'POST'])
@admin_required
def costos_preparacion(crianza_id):
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        try:
            c.execute("""
                INSERT INTO costos_preparacion (crianza_id, fecha, descripcion, valor)
                VALUES (%s,%s,%s,%s)
            """, (crianza_id, request.form.get('fecha', date.today().isoformat()),
                  request.form['descripcion'], float(request.form['valor'])))
            conn.commit()
            flash("Costo registrado", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('costos_preparacion', crianza_id=crianza_id))

    c.execute("SELECT * FROM costos_preparacion WHERE crianza_id=%s ORDER BY fecha", (crianza_id,))
    data = c.fetchall()
    c.execute("SELECT SUM(valor) as total FROM costos_preparacion WHERE crianza_id=%s", (crianza_id,))
    result = c.fetchone()
    total = result['total'] if result and result['total'] else 0
    conn.close()
    return render_template("costos_preparacion.html", data=data, total=total, crianza_id=crianza_id)

# ========================
# PASAR A LISTOS
# ========================

@app.route('/pollos/pasar_listo/<int:crianza_id>', methods=['GET', 'POST'])
@admin_required
def pasar_listo(crianza_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM pollos_crianza WHERE id=%s", (crianza_id,))
    crianza = c.fetchone()
    if not crianza:
        flash("Lote no encontrado", "danger")
        return redirect(url_for('pollos_crianza'))

    if request.method == 'POST':
        try:
            cantidad = int(request.form['cantidad'])
            peso = float(request.form['peso'])
            precio = float(request.form['precio'])
            costo_pollitos = crianza['costo_pollitos'] or 0
            c.execute("SELECT SUM(costo) as total FROM alimento WHERE tipo='pollos'")
            result = c.fetchone()
            costo_alimento = result['total'] if result and result['total'] else 0
            c.execute("SELECT SUM(valor) as total FROM costos_preparacion WHERE crianza_id=%s", (crianza_id,))
            result = c.fetchone()
            costo_prep = result['total'] if result and result['total'] else 0
            costo_total = costo_pollitos + costo_alimento + costo_prep
            c.execute("""
                INSERT INTO pollos_listos (crianza_id, fecha_listo, cantidad, peso_promedio, costo_total, precio_venta_unitario)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (crianza_id, date.today().isoformat(), cantidad, peso, costo_total, precio))
            c.execute("UPDATE pollos_crianza SET estado='FINALIZADO' WHERE id=%s", (crianza_id,))
            conn.commit()
            flash("Lote pasado a disponible para venta", "success")
            return redirect(url_for('pollos_listos'))
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    c.execute("SELECT * FROM control_peso WHERE crianza_id=%s ORDER BY semana DESC LIMIT 1", (crianza_id,))
    ultimo = c.fetchone()
    conn.close()
    return render_template("pasar_listo.html", crianza=crianza, ultimo=ultimo)

# ========================
# POLLOS LISTOS
# ========================

@app.route('/pollos/listos')
@admin_required
def pollos_listos():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT pl.*, pc.lote FROM pollos_listos pl
        JOIN pollos_crianza pc ON pl.crianza_id = pc.id
        ORDER BY pl.fecha_listo DESC
    """)
    data = c.fetchall()
    conn.close()
    return render_template("pollos_listos.html", data=data)

# ========================
# COSTOS GENERALES
# ========================

@app.route('/costos', methods=['GET', 'POST'])
@admin_required
def costos():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        try:
            c.execute("""
                INSERT INTO costos (fecha, categoria, descripcion, valor, producto_relacionado)
                VALUES (%s,%s,%s,%s,%s)
            """, (request.form.get('fecha', date.today().isoformat()), request.form['categoria'],
                  request.form['descripcion'], float(request.form['valor']),
                  request.form.get('producto', 'general')))
            conn.commit()
            flash("Costo registrado", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('costos'))

    c.execute("SELECT * FROM costos ORDER BY fecha DESC")
    data = c.fetchall()
    c.execute("SELECT categoria, SUM(valor) as total FROM costos GROUP BY categoria")
    resumen = c.fetchall()
    conn.close()
    return render_template("costos.html", data=data, resumen=resumen)

@app.route('/costos/eliminar/<int:id>')
@admin_required
def eliminar_costo(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM costos WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Costo eliminado", "info")
    return redirect(url_for('costos'))

# ========================
# REPORTES
# ========================

@app.route('/reportes')
@admin_required
def reportes():
    conn = get_db()
    c = conn.cursor()
    fecha_inicio = request.args.get('inicio', (date.today() - timedelta(days=30)).isoformat())
    fecha_fin = request.args.get('fin', date.today().isoformat())

    c.execute("""
        SELECT p.nombre, SUM(v.cantidad) as cantidad, SUM(v.total) as total
        FROM ventas v JOIN productos p ON v.producto_id = p.id
        WHERE v.estado='ACTIVA' AND v.fecha BETWEEN %s AND %s
        GROUP BY p.nombre
    """, (fecha_inicio, fecha_fin))
    ventas_prod = c.fetchall()

    c.execute("""
        SELECT categoria, SUM(valor) as total FROM costos
        WHERE fecha BETWEEN %s AND %s GROUP BY categoria
    """, (fecha_inicio, fecha_fin))
    costos_cat = c.fetchall()

    total_ventas = sum(v['total'] for v in ventas_prod) if ventas_prod else 0
    total_costos = sum(c_['total'] for c_ in costos_cat) if costos_cat else 0
    ganancia = total_ventas - total_costos

    c.execute("""
        SELECT c.nombre, SUM(v.total) as total
        FROM ventas v JOIN clientes c ON v.cliente_id = c.id
        WHERE v.estado='ACTIVA' AND v.fecha BETWEEN %s AND %s
        GROUP BY c.nombre ORDER BY total DESC LIMIT 5
    """, (fecha_inicio, fecha_fin))
    top_clientes = c.fetchall()

    # Ventas pendientes de pago
    c.execute('''
        SELECT v.*, p.nombre as producto, c.nombre as cliente
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        LEFT JOIN clientes c ON v.cliente_id = c.id
        WHERE v.estado='ACTIVA' AND v.estado_pago='PENDIENTE'
        ORDER BY v.fecha DESC
    ''')
    ventas_pendientes = c.fetchall()

    total_pendiente = sum(v['total'] for v in ventas_pendientes) if ventas_pendientes else 0

    # Ventas a credito (pendientes y parciales)
    c.execute("""
        SELECT v.*, p.nombre as producto, c.nombre as cliente
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        LEFT JOIN clientes c ON v.cliente_id = c.id
        WHERE v.estado='ACTIVA' AND v.estado_pago IN ('PENDIENTE', 'PARCIAL')
        ORDER BY v.fecha DESC
    """)
    ventas_credito = c.fetchall()

    total_por_cobrar = sum(v['total'] - (v['abono'] or 0) for v in ventas_credito)

    conn.close()

    return render_template("reportes.html", ventas_prod=ventas_prod, costos_cat=costos_cat,
                           total_ventas=total_ventas, total_costos=total_costos, ganancia=ganancia,
                           top_clientes=top_clientes, ventas_pendientes=ventas_pendientes,
                           total_pendiente=total_pendiente, total_por_cobrar=total_por_cobrar,
                           fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

# ========================
# GRÁFICAS
# ========================

@app.route('/grafica/ventas')
@admin_required
def grafica_ventas():
    conn = get_db()
    df = pd.read_sql_query("""
        SELECT fecha, SUM(total) as total FROM ventas
        WHERE estado='ACTIVA' AND fecha >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY fecha ORDER BY fecha
    """, conn)
    conn.close()
    if df.empty:
        return "No hay datos"
    plt.figure(figsize=(10, 5))
    plt.plot(df['fecha'], df['total'], marker='o', linewidth=2, color='#2c5530')
    plt.fill_between(df['fecha'], df['total'], alpha=0.3, color='#2c5530')
    plt.xticks(rotation=45)
    plt.title("Ventas Últimos 30 Días", fontsize=14, fontweight='bold')
    plt.xlabel("Fecha")
    plt.ylabel("Total ($)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    img = BytesIO()
    plt.savefig(img, format='png', dpi=100)
    img.seek(0)
    plt.close()
    return send_file(img, mimetype='image/png')

@app.route('/grafica/huevos')
@admin_required
def grafica_huevos():
    conn = get_db()
    df = pd.read_sql_query("""
        SELECT fecha, SUM(cantidad) as total FROM huevos
        WHERE fecha >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY fecha ORDER BY fecha
    """, conn)
    conn.close()
    if df.empty:
        return "No hay datos"
    plt.figure(figsize=(10, 5))
    plt.bar(df['fecha'], df['total'], color='#f4a261')
    plt.xticks(rotation=45)
    plt.title("Producción de Huevos - Últimos 30 Días", fontsize=14, fontweight='bold')
    plt.xlabel("Fecha")
    plt.ylabel("Cantidad")
    plt.tight_layout()
    img = BytesIO()
    plt.savefig(img, format='png', dpi=100)
    img.seek(0)
    plt.close()
    return send_file(img, mimetype='image/png')

@app.route('/grafica/costos_vs_ventas')
@admin_required
def grafica_costos_ventas():
    conn = get_db()
    ventas_df = pd.read_sql_query("""
        SELECT TO_CHAR(fecha, 'YYYY-MM') as mes, SUM(total) as total
        FROM ventas WHERE estado='ACTIVA' GROUP BY mes ORDER BY mes DESC LIMIT 6
    """, conn)
    costos_df = pd.read_sql_query("""
        SELECT TO_CHAR(fecha, 'YYYY-MM') as mes, SUM(valor) as total
        FROM costos GROUP BY mes ORDER BY mes DESC LIMIT 6
    """, conn)
    conn.close()
    fig, ax = plt.subplots(figsize=(10, 5))
    if not ventas_df.empty:
        ax.plot(ventas_df['mes'], ventas_df['total'], marker='o', label='Ventas', color='#2c5530', linewidth=2)
    if not costos_df.empty:
        ax.plot(costos_df['mes'], costos_df['total'], marker='s', label='Costos', color='#e63946', linewidth=2)
    ax.set_title("Comparativo Ventas vs Costos", fontsize=14, fontweight='bold')
    ax.set_xlabel("Mes")
    ax.set_ylabel("Monto ($)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    img = BytesIO()
    plt.savefig(img, format='png', dpi=100)
    img.seek(0)
    plt.close()
    return send_file(img, mimetype='image/png')

# ========================
# EXPORTAR EXCEL
# ========================

@app.route('/exportar/<tabla>')
@admin_required
def exportar(tabla):
    try:
        conn = get_db()
        queries = {
            "ventas": """
                SELECT v.fecha, p.nombre as producto, c.nombre as cliente,
                       v.cantidad, v.precio_unitario, v.total, v.factura_numero, v.estado
                FROM ventas v JOIN productos p ON v.producto_id = p.id
                LEFT JOIN clientes c ON v.cliente_id = c.id
            """,
            "huevos": "SELECT h.*, u.nombre as registrado_por FROM huevos h LEFT JOIN usuarios u ON h.usuario_id=u.id",
            "gallinas": "SELECT g.*, u.nombre as registrado_por FROM gallinas g LEFT JOIN usuarios u ON g.usuario_id=u.id",
            "alimento": "SELECT a.*, u.nombre as registrado_por FROM alimento a LEFT JOIN usuarios u ON a.usuario_id=u.id",
            "costos": "SELECT * FROM costos",
            "clientes": "SELECT * FROM clientes",
            "pollos_crianza": "SELECT * FROM pollos_crianza",
            "control_peso": "SELECT cp.*, u.nombre as registrado_por FROM control_peso cp LEFT JOIN usuarios u ON cp.usuario_id=u.id",
            "pollos_listos": "SELECT * FROM pollos_listos"
        }
        query = queries.get(tabla, f"SELECT * FROM {tabla}")
        df = pd.read_sql_query(query, conn)
        conn.close()
        if df.empty:
            flash("No hay datos para exportar", "warning")
            return redirect(url_for('index'))
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=tabla)
            worksheet = writer.sheets[tabla]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        output.seek(0)
        return send_file(output, download_name=f"{tabla}_{date.today().isoformat()}.xlsx",
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        flash(f"Error al exportar: {e}", "danger")
        return redirect(url_for('index'))

# ========================
# API AJAX
# ========================

@app.route('/api/stock/<int:producto_id>')
@admin_required
def api_stock(producto_id):
    if producto_id == 1:
        return jsonify({"disponible": get_huevos_disponibles()})
    elif producto_id == 2:
        return jsonify({"disponible": get_pollos_disponibles()})
    return jsonify({"disponible": 0})

@app.route('/api/crianza/<int:crianza_id>')
@operario_required
def api_crianza(crianza_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT semana, peso_promedio, cantidad_viva, mortalidad 
        FROM control_peso WHERE crianza_id=%s ORDER BY semana
    """, (crianza_id,))
    controles = c.fetchall()
    conn.close()
    return jsonify([dict(row) for row in controles])

# ========================
# GESTIÓN DE USUARIOS (SOLO ADMIN)
# ========================

@app.route('/usuarios')
@admin_required
def usuarios():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, nombre, rol, activo FROM usuarios ORDER BY rol, nombre")
    data = c.fetchall()
    conn.close()
    return render_template("usuarios.html", data=data)

@app.route('/usuarios/nuevo', methods=['GET', 'POST'])
@admin_required
def nuevo_usuario():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        try:
            c.execute("""
                INSERT INTO usuarios (username, password, nombre, rol)
                VALUES (%s,%s,%s,%s)
            """, (request.form['username'], hash_password(request.form['password']),
                  request.form['nombre'], request.form['rol']))
            conn.commit()
            flash("Usuario creado", "success")
            return redirect(url_for('usuarios'))
        except psycopg2.IntegrityError:
            flash("El usuario ya existe", "danger")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
    conn.close()
    return render_template("nuevo_usuario.html")

@app.route('/usuarios/toggle/<int:id>')
@admin_required
def toggle_usuario(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET activo = CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Estado actualizado", "success")
    return redirect(url_for('usuarios'))

if __name__ == '__main__':
    print("="*50)
    print("GRANJA APP - Servidor iniciado")
    print("Accede desde esta PC: http://localhost:5000")
    print("Accede desde tu celular (misma WiFi): http://<IP-de-tu-PC>:5000")
    print("="*50)
    app.run(debug=True, host='0.0.0.0', port=5000)
