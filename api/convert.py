from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import StreamingResponse, JSONResponse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io

app = FastAPI()

@app.post("/convert")
async def convert_excel(
    file: UploadFile,
    dom: float = Form(0.30),
    lun: float = Form(0.10),
    mar: float = Form(0.10),
    mie: float = Form(0.10),
    jue: float = Form(0.10),
    vie: float = Form(0.15),
    sab: float = Form(0.15),
):
    try:
        # Pesos dinámicos
        weights = {
            6: dom, 0: lun, 1: mar, 2: mie,
            3: jue, 4: vie, 5: sab
        }

        # Leer Excel (intenta con header=1 primero, si no con header=0)
        try:
            df = pd.read_excel(file.file, sheet_name=0, header=1)
        except:
            file.file.seek(0)
            df = pd.read_excel(file.file, sheet_name=0, header=0)

        # Detectar automáticamente las columnas de semana
        week_cols = [c for c in df.columns if str(c).startswith("Semana")]
        if not week_cols:
            return JSONResponse(
                status_code=400,
                content={"error": "No se encontraron columnas que empiecen con 'Semana' en el archivo."}
            )

        # Fecha inicial (ajústala si cambia el calendario real)
        start_date = datetime(2025, 8, 31)
        week_starts = {col: start_date + timedelta(days=7*i) for i, col in enumerate(week_cols)}

        unit_price = 12
        results = []

        # =====================
        # FUNCIÓN DE DISTRIBUCIÓN
        # =====================
        def distribute_weekly_sales(qty, start_date, row):
            daily = {d: qty * w for d, w in weights.items()}
            daily_int = {d: int(np.floor(v)) for d, v in daily.items()}
            diff = qty - sum(daily_int.values())

            if diff > 0:
                residuals = sorted(daily.items(), key=lambda x: x[1] - np.floor(x[1]), reverse=True)
                for i in range(int(diff)):
                    d = residuals[i][0]
                    daily_int[d] += 1

            records = []
            for i in range(7):
                date = start_date + timedelta(days=i)
                q = daily_int.get(i, 0)
                if q > 0:
                    records.append({
                        "Dia": date.strftime("%m/%d/%Y"),
                        "Referencia": row.get("NUEVO SAP", ""),
                        "Número de Catálogo de Fabricante": row.get("Número de catálogo de fabricante", ""),
                        "Código de Barras": row.get("Código de barras", ""),
                        "Categoría": row.get("CATEGORIA", ""),
                        "Descripción artículo/serv.": row.get("Descripción del artículo", ""),
                        "qty": q,
                        "value": f"${q * unit_price:.2f}"
                    })
            return records

        # =====================
        # PROCESAR TODAS LAS SEMANAS Y TODOS LOS SKUs
        # =====================
        for _, row in df.iterrows():
            for col in week_cols:
                qty = row[col]
                if pd.notna(qty) and qty > 0:
                    start_date = week_starts[col]
                    results.extend(distribute_weekly_sales(int(qty), start_date, row))

        if not results:
            return JSONResponse(
                status_code=400,
                content={"error": "El archivo no contenía datos de ventas válidos para procesar."}
            )

        df_result = pd.DataFrame(results)

        # Exportar a Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_result.to_excel(writer, index=False)
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ventas_diarias.xlsx"}
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Ocurrió un error procesando el archivo: {str(e)}"}
        )
