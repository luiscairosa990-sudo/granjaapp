# GranjaApp v2 - Sistema de Gestión Avícola

Aplicación web para la gestión integral de granjas avícolas con roles de usuario y acceso móvil.

## Características

### Roles de Usuario
- **Administrador**: Acceso total (ventas, costos, reportes, gráficas, usuarios)
- **Operario**: Solo registra recolección de huevos y control de peso de pollos

### Módulo Huevos
- Control de gallinas ponedoras
- Registro diario de recolección de huevos (también por operario)
- Control de alimentos
- Stock disponible automático

### Módulo Pollos de Engorde
- Registro de lotes de crianza
- Control semanal de peso y mortalidad (también por operario)
- Costos de preparación
- Paso a "listos para venta"

### Ventas y Facturación
- Registro con descuento automático de inventario
- Facturas PDF profesionales
- Clientes registrados

### Reportes
- Dashboard con KPIs
- Gráficas de ventas, producción y comparativos
- Exportación a Excel

## Instalación

```bash
pip install -r requirements.txt
python app.py
```

## Acceso

### Desde la misma PC:
http://localhost:5000

### Desde tu celular (misma red WiFi):
1. Asegúrate que tu PC y celular estén en la misma red WiFi
2. Abre CMD y ejecuta: `ipconfig`
3. Busca tu "Dirección IPv4" (ej: 192.168.1.50)
4. En tu celular abre: http://192.168.1.50:5000

## Credenciales por defecto

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| admin | 1234 | Administrador |
| operario | 1234 | Operario |

## Crear más usuarios
Ingresa como **admin** y ve a la sección "Usuarios" en el menú.

## Notas
- La base de datos SQLite se crea automáticamente
- Compatible con móvil y PC (responsive)
- Puedes agregar la app a tu pantalla de inicio en el celular
