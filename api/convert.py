from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO

app = FastAPI()

@app.get("/")
def home():
    return {"status": "API funcionando 🚀"}

@app.post("/api/convert")
async def convert_excel(
    file: UploadFile = File(...),
    domingo: float = Form(0.30),
    lunes: float = Form(0.10),
    martes: float = Form(0.10),
    miercoles: float = Form(0.10),
    jueves: float = Form(0.10),
    viernes: float = Form(0.15),
    sabado: float = Form(0.15)
):
    try:
        # =====================
        # LEER ARCHIVO
        # =====================
        content = await file.read()
        xls = pd.ExcelFile(BytesIO(content))

        # usar siempre la primera hoja
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=1)

        # =====================
        # CONFIGURACIÓN
        # =====================
        weights = {
            6: domingo,
            0: lunes,
            1: martes,
            2: miercoles,
            3: jueves,
            4: viernes,
            5: sabado
        }
        unit_price = 12
        week_cols = [c for c in df.columns if str(c).startswith("Semana")]
        start_date = datetime(2025, 8, 31)
        week_starts = {col: start_date + timedelta(days=7*i) for i, col in enumerate(week_cols)}

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
        # PROCESAR
        # =====================
        results = []
        for _, row in df.iterrows():
            for col in week_cols:
                qty = row[col]
                if pd.notna(qty) and qty > 0:
                    start_date = week_starts[col]
                    results.extend(distribute_weekly_sales(int(qty), start_date, row))

        df_result = pd.DataFrame(results)

        # =====================
        # EXPORTAR
        # =====================
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_result.to_excel(writer, index=False)
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ventas_diarias.xlsx"}
        )

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

