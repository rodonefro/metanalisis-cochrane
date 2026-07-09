---
name: cochrane-metaanalysis-report
description: Genera un reporte completo de revisión sistemática y metaanálisis siguiendo
  la estructura oficial del Manual Cochrane, listo para publicar como documento Word
  (.docx). Úsala siempre que el usuario pida un metaanálisis, una revisión sistemática
  Cochrane, un reporte de evidencia con GRADE, un reporte de sesgo de publicación con
  funnel plot, o cualquier documento de síntesis de evidencia clínica que requiera
  estructura PICO, tablas GRADE, diagrama de flujo PRISMA y análisis estadístico.
  También aplica cuando el usuario proporcione datos de estudios incluidos (OR, RR,
  IC 95%, I²) y pida organizarlos en formato Cochrane, generar una tabla Summary of
  Findings, o estructurar una discusión con implicaciones para la práctica. Actívala
  ante frases como "hazme el metaanálisis", "necesito el reporte Cochrane", "genera
  la revisión sistemática", "arma el documento con GRADE", "incluye el funnel plot"
  o cualquier variante orientada a producir documentos de síntesis de evidencia de
  nivel publicación.
metadata:
  display_name: Reporte de Metaanálisis Cochrane
compatibility: Claude Code
---

# Reporte de Metaanálisis Cochrane

Genera documentos de revisión sistemática y metaanálisis con la estructura completa
del Manual Cochrane (2023), listos para publicar. El producto final es un reporte
con todas las secciones requeridas, Funnel Plot embebido y Tabla GRADE visual.

---

## Contexto de la plataforma

Esta skill se ejecuta dentro de la plataforma MetaAnálisis Cochrane
(`backend/` FastAPI + `frontend/` React + Vite). Los datos ya están en la base de
datos SQLite (SQLAlchemy). No es necesario parsear archivos externos — usa los
endpoints existentes de la API para obtener la revisión, estudios y resultados.

---

## Paso 1 — Obtener datos de la revisión

Lee la revisión completa desde la base de datos usando el endpoint:
```
GET /reviews/{review_id}
```
Extrae y consolida:
1. Pregunta PICO (población, intervención, comparador, desenlaces)
2. Campos PRISMA ya guardados (prisma_screened, prisma_assessed, prisma_included, etc.)
3. Secciones de texto ya generadas (abstract, background, objectives, methods, results, discussion)
4. Estudios incluidos con todos sus campos numéricos y cualitativos
5. Resultado del último análisis (results_json con pooled effect, I², tau², Q)

---

## Paso 2 — Generar Funnel Plot

Usa el endpoint existente:
```
GET /reviews/{review_id}/analysis/funnel
```
Obtiene el funnel plot como base64 PNG.

Especificaciones del Funnel Plot (ya implementadas en `backend/app/services/plots.py`):
- Eje Y: Error estándar (SE)
- Eje X: log(OR) o log(RR) según effect_measure de la revisión
- Un punto por estudio incluido
- Región sombreada al 95% IC
- Líneas vertical (x=0) y punteada (efecto combinado)
- Pie de figura: interpretación de asimetría como señal de sesgo de publicación

---

## Paso 3 — Generar Tabla GRADE

Usa el endpoint existente:
```
GET /reviews/{review_id}/analysis/grade
```
Obtiene la tabla GRADE como base64 PNG.

Especificaciones (ya implementadas en `backend/app/services/plots.py`):
- Columnas: Intervención | Comparador | N estudios (N pacientes) | Estimador (IC 95%) | I² | Certeza GRADE | Importancia
- Certeza GRADE con símbolos: ⊕⊕⊕⊕ Alta / ⊕⊕⊕○ Moderada / ⊕⊕○○ Baja / ⊕○○○ Muy baja
- Colores: verde (alta), azul (moderada), ámbar (baja), naranja/rojo (muy baja)

---

## Paso 4 — Exportar documento

### Opción A — PDF (ya implementado)
```
GET /reviews/{review_id}/export/pdf
```
Usa ReportLab para generar el PDF completo con:
- Portada con PICO y metadatos
- Abstract estructurado
- Secciones 1-6 (Background → Authors' conclusions)
- Tabla 1. Características de los estudios incluidos (tarjetas verticales por estudio)
- Diagrama PRISMA 2020
- Forest plot, Funnel plot
- Tabla GRADE en apéndice
- Referencias

### Opción B — Word DOCX (endpoint a implementar)
```
GET /reviews/{review_id}/export/docx
```
Usa `python-docx` siguiendo la misma estructura que el PDF pero en formato editable.
Implementar en `backend/app/routers/export.py` junto al endpoint PDF existente.

---

## Estructura Cochrane 2023 obligatoria

| Sección | Contenido clave |
|---|---|
| Abstract | Background, Objectives, Selection criteria, Data collection, Main results, Conclusions |
| 1. Background | Condición, Intervención, Mecanismo, Por qué esta revisión |
| 2. Objectives | Pregunta PICO expresada como objetivo |
| 3. Methods | Criterios, Búsqueda, Selección, Extracción, RoB, Medidas de efecto, Heterogeneidad |
| 4. Results | Descripción estudios, PRISMA, Características incluidos, RoB, Efectos |
| 5. Discussion | Resumen, Completitud, Calidad evidencia, Sesgos revisión, Comparación con literatura |
| 6. Conclusions | Implicaciones práctica + investigación |
| Declaraciones | Conflictos de interés |
| Referencias | Estudios incluidos + adicionales |
| Apéndices | GRADE, Estrategias búsqueda, Estudios excluidos |

---

## Generación de secciones con IA

Los endpoints de generación ya disponibles en la plataforma:

```
POST /reviews/{review_id}/generate/abstract
POST /reviews/{review_id}/generate/background
POST /reviews/{review_id}/generate/objectives
POST /reviews/{review_id}/generate/methods
POST /reviews/{review_id}/generate/results
POST /reviews/{review_id}/generate/discussion
POST /reviews/{review_id}/generate/references
```

Todos usan Claude Opus con `thinking={"type": "adaptive"}` y generan texto en español
conforme al Manual Cochrane 2023. Llama a estos endpoints en secuencia para completar
el documento antes de exportar.

---

## Checklist de calidad antes de exportar

- [ ] PICO completo (población, intervención, comparador, desenlaces)
- [ ] Al menos 2 estudios incluidos con datos numéricos
- [ ] Metaanálisis ejecutado (`POST /analysis/run`)
- [ ] Forest plot generado (`GET /analysis/forest`)
- [ ] Funnel plot generado (`GET /analysis/funnel`)
- [ ] Tabla GRADE generada (`GET /analysis/grade`)
- [ ] Diagrama PRISMA configurado (campos `prisma_*` de la revisión)
- [ ] Secciones de texto generadas con IA o redactadas manualmente
- [ ] Referencias completadas
