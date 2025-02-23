#!/usr/bin/env python
# coding: utf-8

# ### Importar Librerías

# In[25]:


import xmlrpc.client
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


# ### Parametros para conexion a Odoo

# In[27]:


url = 'https://movingfood.konos.cl'  # URL de tu instancia Odoo
db = 'movingfood-mfood-erp-main-7481157'  # Nombre exacto de la base de datos
username = 'logistica@movingfood.cl'  # Usuario de Odoo
api_key = '7a1e4e24b1f34abbe7c6fd93fd5fd75dccda90a6'  # Clave API generada

# AUTENTICACION MEDIANTE PROTOCOLO XML-RPC Y CONEXION AL ENDPOINT DE USUARIO 'COMMON'
try:
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, api_key, {}) # Obtiene User ID que indica que es válida la conexion
    if not uid:
        print('Error en la autenticación. Verifica tus credenciales o la clave API.')
        exit()
    print(f"Autenticación exitosa. UID: {uid}")
except Exception as e:
    print(f"Error durante la conexión: {e}")
    exit()

# AUTENTICACION MEDIANTE PROTOCOLO XML-RPC Y CONEXION AL ENDPOINT DE OBJETOS 'OBJECT'
models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')


# ### Leer Datos de Odoo

# In[31]:


# FUNCION: Leer stock de productos en Odoo con filtro por uso interno
def leer_stock_productos():
    try:
        # Definir los campos a extraer del modelo `stock.quant`
        fields = [
            'product_id',       # Producto (Many2one → `product.product`)
            'location_id',      # Ubicación/Bodega (Many2one → `stock.location`)
            'quantity',         # Cantidad disponible en stock
            'reserved_quantity' # Cantidad reservada
        ]

        # Obtener IDs de ubicaciones con uso 'internal'
        location_ids = models.execute_kw(db, uid, api_key, 'stock.location', 'search', [[('usage', '=', 'internal')]])

        # Consultar registros de stock filtrando por ubicaciones internas
        domain = [('location_id', 'in', location_ids)]
        stock_records = models.execute_kw(db, uid, api_key, 'stock.quant', 'search_read', [domain], {'fields': fields})

        if not stock_records:
            print("No se encontraron registros de stock en ubicaciones internas.")
            return pd.DataFrame()

        # Convertir a DataFrame
        df_stock = pd.DataFrame(stock_records)

        # Procesar campos Many2one para extraer nombres legibles
        df_stock['Producto'] = df_stock['product_id'].apply(lambda x: x[1] if isinstance(x, list) else None)  # Nombre del producto
        df_stock['Bodega'] = df_stock['location_id'].apply(lambda x: x[1] if isinstance(x, list) else None)

        # Seleccionar columnas finales
        df_stock = df_stock[['Producto', 'Bodega', 'quantity', 'reserved_quantity']]

        # Renombrar columnas para mayor claridad
        df_stock.rename(columns={
            'quantity': 'Cantidad Disponible',
            'reserved_quantity': 'Cantidad Reservada'
        }, inplace=True)

        return df_stock

    except Exception as e:
        print(f"Error al leer stock de productos: {e}")
        return pd.DataFrame()

# FUNCION: Cargar datos en Google Sheets
def cargar_en_google_sheets(dataframe, key_path, sheet_id, sheet_name, start_row=3):
    try:
        # Autenticación con Google Sheets
        creds = Credentials.from_service_account_file(key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        service = build('sheets', 'v4', credentials=creds)
        

        # Definir las columnas a limpiar (B, C, D, E) desde la fila 3
        clear_range = f"{sheet_name}!B{start_row}:E"
        sheet = service.spreadsheets()
        sheet.values().clear(spreadsheetId=sheet_id, range=clear_range).execute()

        # Convertir DataFrame a lista para cargar en Sheets (sin encabezados)
        data = dataframe.values.tolist()

        # Definir el rango inicial dinámico para la carga de datos
        data_range = f"{sheet_name}!B{start_row}"

        # Cargar los datos en el rango definido
        sheet.values().update(
            spreadsheetId=sheet_id,
            range=data_range,
            valueInputOption="RAW",
            body={"values": data}
        ).execute()
        print(f"Datos cargados exitosamente en Google Sheets desde la fila {start_row}: {sheet_name}")

    except Exception as e:
        print(f"Error al cargar datos en Google Sheets: {e}")

# EJECUTAR LA CONSULTA
df_stock = leer_stock_productos()

# CARGAR EN GOOGLE SHEETS
key_path = 'key.json'
sheet_id = '1HaFlJZOFLQHqNJMPAHitsuUBcxbOXxVsvB_yzvz08Ok'
sheet_name = 'Inventario Actual'
cargar_en_google_sheets(df_stock, key_path, sheet_id, sheet_name)


# In[ ]:




