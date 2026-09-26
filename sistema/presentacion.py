"""Formateo de resultados en texto para la consola."""
from __future__ import annotations

from typing import List, Sequence

from .busqueda import Resultado
from .red import RedTransporte

NOMBRES_ALGORITMO = {
    "a_estrella": "A* (A estrella)",
    "costo_uniforme": "Costo uniforme",
    "voraz": "Primero el mejor voraz",
    "amplitud": "Primero en amplitud",
}


def instrucciones(red: RedTransporte, r: Resultado, detalle: bool = False) -> List[str]:
    """Agrupa los pasos en tramos legibles: abordar -> viajar N paradas -> transbordo..."""
    lineas: List[str] = []
    n = 0
    tramo_estaciones: List[str] = []
    tramo_min = 0.0
    tramo_troncal = None

    def cerrar_tramo():
        nonlocal tramo_estaciones, tramo_min
        if len(tramo_estaciones) > 1:
            lineas.append(f"    Viaje {len(tramo_estaciones) - 1} parada(s) hasta {tramo_estaciones[-1]} "
                          f"(~{tramo_min:.1f} min).")
            if detalle:
                lineas.append("      " + " -> ".join(tramo_estaciones))
        tramo_estaciones, tramo_min = [], 0.0

    for p in r.pasos:
        if p.accion == "abordar":
            cerrar_tramo()
            n += 1
            espera = f" (espera ~{p.minutos:.0f} min)" if p.minutos else ""
            lineas.append(f" {n}. Aborde la troncal {red.nombre_troncal(p.troncal)} en {p.desde}{espera}.")
            tramo_troncal, tramo_estaciones = p.troncal, [p.desde]
        elif p.accion == "viajar":
            if not tramo_estaciones:
                tramo_estaciones = [p.desde]
            tramo_estaciones.append(p.hacia)
            tramo_min += p.minutos
        elif p.accion == "transbordo":
            cerrar_tramo()
            n += 1
            lineas.append(f" {n}. Transbordo en {p.desde}: de {red.nombre_troncal(tramo_troncal)} "
                          f"a {red.nombre_troncal(p.troncal)} (~{p.minutos:.0f} min).")
            tramo_troncal, tramo_estaciones = p.troncal, [p.desde]
        elif p.accion == "caminar":
            cerrar_tramo()
            n += 1
            lineas.append(f" {n}. Camine de {p.desde} a {p.hacia} por la conexión peatonal "
                          f"(~{p.minutos:.0f} min).")
    cerrar_tramo()
    return lineas


def formatear_ruta(red: RedTransporte, r: Resultado, detalle: bool = False) -> str:
    salida = [f"=== Ruta: {r.origen} -> {r.destino} ===",
              f"Algoritmo: {NOMBRES_ALGORITMO.get(r.algoritmo, r.algoritmo)} | Criterio: {r.criterio}"]
    if red.cerradas:
        salida.append(f"Estaciones cerradas: {', '.join(red.cerradas)}")
    salida.append("")
    if not r.encontrado:
        salida.append("No existe una ruta con las condiciones actuales de la red.")
    elif not r.pasos:
        salida.append("El origen y el destino son la misma estación.")
    else:
        salida.extend(instrucciones(red, r, detalle))
        salida.append("")
        salida.append(f"Resumen: ~{r.minutos:.1f} min | {r.transbordos} transbordo(s) | "
                      f"{r.paradas} parada(s)")
    salida.append(f"Búsqueda: {r.nodos_expandidos} nodos expandidos, {r.nodos_generados} generados, "
                  f"frontera máx. {r.max_frontera}, {r.tiempo_ms:.2f} ms")
    return "\n".join(salida)


def tabla(encabezados: Sequence[str], filas: Sequence[Sequence[object]]) -> str:
    textos = [[str(c) for c in f] for f in filas]
    anchos = [max(len(h), *(len(f[i]) for f in textos)) if textos else len(h)
              for i, h in enumerate(encabezados)]
    linea = lambda celdas: " | ".join(c.ljust(anchos[i]) for i, c in enumerate(celdas))
    return "\n".join([linea(encabezados), "-+-".join("-" * a for a in anchos), *(linea(f) for f in textos)])


def formatear_comparacion(resultados: Sequence[Resultado]) -> str:
    filas = []
    for r in resultados:
        if r.encontrado:
            filas.append([NOMBRES_ALGORITMO.get(r.algoritmo, r.algoritmo), f"{r.minutos:.1f}", r.transbordos,
                          r.paradas, r.nodos_expandidos, r.nodos_generados, f"{r.tiempo_ms:.2f}"])
        else:
            filas.append([NOMBRES_ALGORITMO.get(r.algoritmo, r.algoritmo), "sin ruta", "-", "-",
                          r.nodos_expandidos, r.nodos_generados, f"{r.tiempo_ms:.2f}"])
    return tabla(["Algoritmo", "Minutos", "Transb.", "Paradas", "Expandidos", "Generados", "ms"], filas)
