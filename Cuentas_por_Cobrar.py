#!/usr/bin/env python
# coding: utf-8

# ### Importar Librerías

# In[104]:


import xmlrpc.client
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


# ### Parametros para conexion a Odoo

# In[107]:


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

# In[111]:


# FUNCION: Obtener IDs de vendedores por nombre
def obtener_ids_vendedores(nombres_vendedores):
    try:
        # Consultar registros desde el modelo `res.users`
        domain = [('name', 'in', nombres_vendedores)]
        fields = ['id', 'name']
        vendedores = models.execute_kw(db, uid, api_key, 'res.users', 'search_read', [domain], {'fields': fields})

        if not vendedores:
            print("No se encontraron vendedores con los nombres proporcionados.")
            return []

        # Convertir a un diccionario para facilitar el acceso
        vendedores_dict = {v['name']: v['id'] for v in vendedores}
        ## print(f"Vendedores encontrados: {vendedores_dict}")
        return list(vendedores_dict.values())

    except Exception as e:
        print(f"Error al obtener IDs de vendedores: {e}")
        return []

# FUNCION: Leer facturas de venta y boletas no pagadas
def leer_facturas_no_pagadas(vendedores):
    # Filtro de dominio
    domain = [
        ('move_type', 'in', ['out_invoice', 'out_receipt']),  # Solo Facturas de Venta y Boletas
        ('payment_state', 'in', ['not_paid', 'partial']),  # Estado de pago no pagado o parcialmente pagado
        ('state', '=', 'posted'),  # Solo documentos publicados
        ('invoice_user_id', 'in', vendedores),  # Filtrar por vendedores específicos

        ('l10n_latam_document_type_id', '!=', False) # Eliminar TipoDocumento vacios, para no incluir facturas del 2021.
    ]

    try:
        # Consultar registros desde el modelo `account.move`
        fields = [
            'id', 'name', 'invoice_date', 'invoice_origin', 'invoice_date_due', 'payment_state',
            'partner_id', 'partner_shipping_id', 'amount_total', 'amount_residual', 'invoice_user_id', 'payment_state'
        ]
        facturas = models.execute_kw(db, uid, api_key, 'account.move', 'search_read', [domain], {'fields': fields})

        if not facturas:
            print("No se encontraron facturas o boletas no pagadas.")
            return pd.DataFrame()

        # Convertir a DataFrame
        df_facturas = pd.DataFrame(facturas)

        # Procesar campos Many2one
        campos_many2one = ['partner_id', 'partner_shipping_id', 'invoice_user_id']
        for campo in campos_many2one:
            df_facturas[f'{campo}_id'] = df_facturas[campo].apply(lambda x: x[0] if isinstance(x, list) else None)
            df_facturas[f'{campo}_name'] = df_facturas[campo].apply(lambda x: x[1] if isinstance(x, list) else None)

        # Convertir valores de `payment_state`
        estado_pago_map = {
            'not_paid': 'No Pagadas',
            'partial': 'Pagado Parcialmente'
        }
        df_facturas['payment_state'] = df_facturas['payment_state'].map(estado_pago_map)
        
        # Obtener información adicional desde `res.partner`
        partner_ids = df_facturas['partner_id_id'].dropna().unique().tolist()
        partner_fields = ['id', 'vat', 'property_payment_term_id', 'credit_limit', 'visit_day']
        partners = models.execute_kw(db, uid, api_key, 'res.partner', 'read', [partner_ids], {'fields': partner_fields})
        df_partners = pd.DataFrame(partners)

        # Procesar campos Many2one en `res.partner`
        if 'property_payment_term_id' in df_partners:
            df_partners['property_payment_term_name'] = df_partners['property_payment_term_id'].apply(
                lambda x: x[1] if isinstance(x, list) else None
            )

        # Renombrar columnas de `res.partner`
        df_partners.rename(columns={
            'id': 'partner_id_id',
            'vat': 'RUT Cliente',
            'credit_limit': 'Límite de Crédito',
            'visit_day': 'Día de Visita',
            'property_payment_term_name': 'Plazo de Pago'
        }, inplace=True)

        # Combinar la información de `account.move` con `res.partner`
        df_facturas = df_facturas.merge(df_partners, on='partner_id_id', how='left')

        # Calcular días de atraso
        today = datetime.now().date()
        df_facturas['invoice_date_due'] = pd.to_datetime(df_facturas['invoice_date_due'], errors='coerce')
        df_facturas['Días de Atraso'] = ((df_facturas['invoice_date_due'] - pd.Timestamp(today)).dt.days *-1)

        # Ordenar por días de atraso de mayor a menor
        df_facturas.sort_values(by='Días de Atraso', ascending=False, inplace=True)

        
        # Seleccionar columnas necesarias
        columnas_finales = [
            'RUT Cliente', 'partner_id_name', 'invoice_date', 'name', 'invoice_date_due', 'invoice_origin', 'payment_state',
            'amount_total', 'amount_residual','Días de Atraso', 'invoice_user_id_name', 'Día de Visita',
            'Plazo de Pago', 'Límite de Crédito'
        ]
        df_facturas = df_facturas[columnas_finales]

        # Renombrar columnas
        df_facturas.rename(columns={
            'name': 'Número de Documento',
            'invoice_date': 'Fecha de la factura',
            'invoice_origin': 'Documento Origen',
            'invoice_date_due': 'Fecha Vencimiento',
            'payment_state': 'Estado de Pago',
            'partner_id_name': 'Cliente',
            'amount_total': 'Total',
            'amount_residual': 'Saldo',
            'invoice_user_id_name': 'Vendedor'
        }, inplace=True)

        return df_facturas

    except Exception as e:
        print(f"Error al leer facturas no pagadas: {e}")
        return pd.DataFrame()

# FUNCION: Obtener el ID de la hoja en Google Sheets
def obtener_sheet_id(service, spreadsheet_id, sheet_name):
    try:
        # Obtener la metadata del archivo de Google Sheets
        sheets_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheets_metadata.get("sheets", [])

        for sheet in sheets:
            if sheet["properties"]["title"] == sheet_name:
                return sheet["properties"]["sheetId"]

        print(f"No se encontró la hoja con el nombre: {sheet_name}")
        return None
    except Exception as e:
        print(f"Error al obtener sheetId: {e}")
        return None

# FUNCION: Cargar datos en Google Sheets
def cargar_en_google_sheets(dataframe, key_path, sheet_id, sheet_name, start_row=3):
    try:
        # Convertir columnas datetime a string
        if not dataframe.empty:
            for column in dataframe.select_dtypes(include=['datetime', 'datetime64[ns]']).columns:
                dataframe[column] = dataframe[column].dt.strftime('%Y-%m-%d')
        
        # Autenticación con Google Sheets
        creds = Credentials.from_service_account_file(key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        service = build('sheets', 'v4', credentials=creds)
        spreadsheet = service.spreadsheets()

        # Obtener el sheetId correcto
        sheet_id_correcto = obtener_sheet_id(service, sheet_id, sheet_name)
        if sheet_id_correcto is None:
            return
        
        # Quitar filtros en la hoja antes de actualizar los datos
        request_body = {
            "requests": [
                {"clearBasicFilter": {"sheetId": sheet_id_correcto}}
            ]
        }
        spreadsheet.batchUpdate(spreadsheetId=sheet_id, body=request_body).execute()
        
        # Convertir DataFrame a lista para cargar en Sheets (sin encabezados)
        data = dataframe.values.tolist()

        # Determinar el rango dinámico basado en el número de columnas del DataFrame
        num_columns = dataframe.shape[1]
        last_column = chr(64 + num_columns)  # Convierte el índice de columna a letra (A, B, C, ..., Z, AA, AB, etc.)
        data_range = f"{sheet_name}!A{start_row}:{last_column}"  # Ajusta el rango al número de columnas

        # Limpiar solo el rango correspondiente a los datos
        sheet = service.spreadsheets()
        sheet.values().clear(spreadsheetId=sheet_id, range=data_range).execute()
        
        # Cargar los datos en el rango definido
        spreadsheet.values().clear(spreadsheetId=sheet_id, range=data_range).execute()
        sheet.values().update(
            spreadsheetId=sheet_id,
            range=data_range,
            valueInputOption="RAW",
            body={"values": data}
        ).execute()
        print(f"Datos cargados exitosamente en Google Sheets desde la fila {start_row}: {sheet_name}")

    except Exception as e:
        print(f"Error al cargar datos en Google Sheets: {e}")

# NOMBRES DE VENDEDORES
nombres_vendedores = ['DANIEL CHACON','HENRY MENDOZA','ANDERSON MEJIAS','LENNYS OJEDA','LUIS DIAZ','FELIX AVILAN',
                     'JORGE KEWAYFATI','ELVER ROMERO','NEEDMI CASANOVA','MAITE DE SANTIAGO','ORLANDO LUGO',
                     'AURA DUEZ','OLGA LINARES','JUAN MORA','SANDRA SEGNINI','ANTONIO ANDRES TERAN','ROBERTO SEPULVEDA','LUIS BELLO','PEDRO SOTO','CAMILA FARFAN','MARIA EUGENIA LANDAETA']

# OBTENER IDs DE VENDEDORES
vendedores_ids = obtener_ids_vendedores(nombres_vendedores)

# LEER LAS FACTURAS
facturas_df = leer_facturas_no_pagadas(vendedores_ids)

# CARGAR EN GOOGLE SHEETS
key_path = 'key.json'
sheet_id = '1o89d2Ird1ZU1XBJipj2wLkhLrLJQCOjfpJq5KhMypjI'
sheet_name = 'Facturas No Pagadas Odoo'

cargar_en_google_sheets(facturas_df, key_path, sheet_id, sheet_name)


# In[ ]:




