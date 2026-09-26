#!/usr/bin/env python3
"""
Sistema inteligente basado en conocimiento para encontrar la mejor ruta
entre dos estaciones de TransMilenio (Bogotá).

Uso rápido:
    python main.py                                   # modo interactivo
    python main.py ruta "Portal Norte" "Portal Américas"
    python main.py comparar "Portal 80" "Universidades"
    python main.py consultar "transbordo(E, T1, T2)"
    python main.py explicar transbordo Ricaurte E F
    python main.py estaciones --troncal K
    python main.py reglas
    python main.py escenarios --salida resultados_pruebas.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import Callable, List, Optional, Sequence

from sistema.busqueda import ALGORITMOS, ProblemaRuta, Resultado, buscar_ruta
from sistema.logica import ErrorLogico, formatear_hecho, formatear_termino
from sistema.presentacion import formatear_comparacion, formatear_ruta, tabla
from sistema.red import RedTransporte


def _utf8_en_consola() -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")  # Windows (cmd/PowerShell)
        except (AttributeError, ValueError):
            pass


def _convertir(valor: str):
    try:
        return int(valor)
    except ValueError:
        try:
            return float(valor)
        except ValueError:
            return valor


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_ruta(args) -> None:
    red = RedTransporte(cerradas=args.cerrar or [])
    r = buscar_ruta(red, args.origen, args.destino, args.algoritmo, args.criterio)
    print(formatear_ruta(red, r, detalle=args.detalle))


def cmd_comparar(args) -> None:
    red = RedTransporte(cerradas=args.cerrar or [])
    resultados = [buscar_ruta(red, args.origen, args.destino, a, args.criterio) for a in ALGORITMOS]
    print(f"=== Comparación de estrategias: {resultados[0].origen} -> {resultados[0].destino} "
          f"(criterio: {args.criterio}) ===\n")
    print(formatear_comparacion(resultados))
    print("\nRuta encontrada por A*:")
    print("  " + " -> ".join(resultados[0].estaciones_ruta))


def cmd_consultar(args) -> None:
    red = RedTransporte(cerradas=args.cerrar or [])
    filas = red.kb.consultar(args.consulta)
    if not filas:
        print("No hay resultados (la consulta es falsa en la base de conocimiento).")
        return
    if not filas[0]:
        print("Verdadero.")
        return
    columnas = list(filas[0])
    print(tabla(columnas, [[f.get(c, "") for c in columnas] for f in filas[: args.limite]]))
    if len(filas) > args.limite:
        print(f"... ({len(filas) - args.limite} resultados más; use --limite)")
    print(f"\n{len(filas)} resultado(s).")


def cmd_explicar(args) -> None:
    red = RedTransporte(cerradas=args.cerrar or [])
    valores = []
    for v in args.argumentos:
        c = _convertir(v)
        # Permite escribir nombres sin tildes: se corrige si es una estación
        if isinstance(c, str):
            try:
                c = red.resolver_nombre(c) if len(c) > 1 else c
            except ValueError:
                pass
        valores.append(c)
    print(red.kb.explicar((args.predicado, tuple(valores))))


def cmd_estaciones(args) -> None:
    red = RedTransporte()
    if args.troncal:
        codigo = args.troncal.upper()
        if codigo not in red.troncales:
            raise ValueError(f"Troncal desconocida: {codigo}. Opciones: {', '.join(sorted(red.troncales))}")
        # Recorre la troncal desde su cabecera usando los hechos siguiente/3
        cabeceras = [e for e, _ in red.kb.buscar("cabecera", None, codigo)]
        orden, actual = [], (cabeceras[0] if cabeceras else None)
        while actual is not None:
            orden.append(actual)
            sig = [b for _, b, _ in red.kb.buscar("siguiente", actual, None, codigo)]
            actual = sig[0] if sig else None
        consecutivos = set(zip(orden, orden[1:]))
        ramales = [(a, b) for a, b, _ in red.kb.buscar("siguiente", None, None, codigo)
                   if (a, b) not in consecutivos]
        print(f"Troncal {red.nombre_troncal(codigo)}: {len(orden) + len(ramales)} estaciones")
        for i, e in enumerate(orden, 1):
            extra = ", ".join(t for t in red.troncales_de(e) if t != codigo)
            print(f"  {i:2}. {e}" + (f"   [transbordo a {extra}]" if extra else ""))
        for a, b in ramales:
            print(f"  Ramal/interconector: {a} -> {b}")
        return
    filas = [[e, ", ".join(red.troncales_de(e))] for e in red.estaciones]
    print(tabla(["Estación", "Troncales"], filas))
    print(f"\n{len(filas)} estaciones en {len(red.troncales)} troncales.")


def cmd_reglas(args) -> None:
    red = RedTransporte()
    print("=== Reglas de la base de conocimiento ===")
    for r in red.kb.reglas:
        print(f"  {r.etiqueta:>4}: {r}")
    e = red.estadisticas
    print("\n=== Encadenamiento hacia adelante ===")
    print(f"  Hechos base: {e.hechos_base} | Hechos derivados: {e.hechos_derivados} | "
          f"Reglas: {e.reglas} | Estratos: {e.estratos} | Iteraciones: {e.iteraciones}")


# ---------------------------------------------------------------------------
# Escenarios de prueba (evidencia para el documento de pruebas)
# ---------------------------------------------------------------------------

class Escenario:
    def __init__(self, nombre: str, origen: str, destino: str, esperado: str,
                 verificar: Callable[[Resultado], bool], cerradas: Sequence[str] = (),
                 criterio: str = "tiempo", comparar: bool = False):
        self.nombre, self.origen, self.destino = nombre, origen, destino
        self.esperado, self.verificar = esperado, verificar
        self.cerradas, self.criterio, self.comparar = list(cerradas), criterio, comparar

    def comando(self) -> str:
        base = "comparar" if self.comparar else "ruta"
        partes = [f'python main.py {base} "{self.origen}" "{self.destino}"']
        if self.criterio != "tiempo":
            partes.append(f"--criterio {self.criterio}")
        if self.cerradas:
            partes.append("--cerrar " + " ".join(f'"{c}"' for c in self.cerradas))
        return " ".join(partes)


ESCENARIOS = [
    Escenario("Viaje sobre una sola troncal", "Portal Norte", "Calle 100",
              "Ruta directa por la troncal B, sin transbordos.",
              lambda r: r.encontrado and r.transbordos == 0),
    Escenario("Un transbordo (norte -> centro)", "Portal Norte", "Av. Jiménez",
              "Troncal B hasta Héroes y transbordo a la troncal A (Caracas).",
              lambda r: r.encontrado and r.transbordos == 1 and "Héroes" in r.estaciones_ruta),
    Escenario("Elección entre corredores alternativos", "Portal Norte", "Ricaurte",
              "Existen dos caminos (NQS o Caracas + Américas); se elige el de menor tiempo.",
              lambda r: r.encontrado and "Paloquemao" in r.estaciones_ruta, comparar=True),
    Escenario("Viaje largo occidente-occidente", "Portal 80", "Portal Américas",
              "A* encuentra el mismo costo que costo uniforme expandiendo menos nodos.",
              lambda r: r.encontrado, comparar=True),
    Escenario("Uso de conexión peatonal", "Portal El Dorado", "Museo del Oro",
              "Troncal K hasta Universidades, túnel peatonal a Las Aguas y troncal J.",
              lambda r: r.encontrado and any(p.accion == "caminar" for p in r.pasos)),
    Escenario("Estación cerrada (replanificación)", "Portal Norte", "Ricaurte",
              "Con Paloquemao cerrada, la ruta evita esa estación y usa otro corredor.",
              lambda r: r.encontrado and "Paloquemao" not in r.estaciones_ruta, cerradas=["Paloquemao"]),
    Escenario("La búsqueda voraz no garantiza la mejor ruta", "Escuela Militar", "U. Nacional",
              "Voraz se deja guiar solo por la cercanía al destino y produce una ruta más lenta; A* es óptimo.",
              lambda r: r.encontrado and r.minutos < buscar_ruta(RedTransporte(), r.origen, r.destino, "voraz").minutos,
              comparar=True),
    Escenario("Sin ruta posible", "Portal Norte", "Calle 100",
              "Con Toberín cerrada, Portal Norte queda aislado: el sistema informa que no hay ruta.",
              lambda r: not r.encontrado, cerradas=["Toberín"]),
    Escenario("Nombres sin tildes ni mayúsculas", "heroes", "americas av boyaca",
              "El sistema reconoce 'Héroes' y 'Américas - Av. Boyacá'.",
              lambda r: r.encontrado and r.origen == "Héroes"),
    Escenario("Origen igual al destino", "Calle 45", "Calle 45",
              "Ruta vacía, costo 0.",
              lambda r: r.encontrado and not r.pasos),
]


def cmd_escenarios(args) -> None:
    md: List[str] = [
        "# Resultados de pruebas - Ruta óptima en TransMilenio",
        "",
        f"Generado automáticamente el {datetime.now():%Y-%m-%d %H:%M} con `python main.py escenarios`.",
        "",
    ]
    aprobados = 0
    for i, esc in enumerate(ESCENARIOS, 1):
        red = RedTransporte(cerradas=esc.cerradas)
        r = buscar_ruta(red, esc.origen, esc.destino, "a_estrella", esc.criterio)
        ok = esc.verificar(r)
        aprobados += ok
        md += [f"## Prueba {i}. {esc.nombre}", "",
               f"- **Comando:** `{esc.comando()}`",
               f"- **Resultado esperado:** {esc.esperado}",
               f"- **Veredicto:** {'APROBADA' if ok else 'FALLIDA'}", "",
               "```text", formatear_ruta(red, r), "```", ""]
        if esc.comparar:
            res = [buscar_ruta(red, esc.origen, esc.destino, a, esc.criterio) for a in ALGORITMOS]
            md += ["Comparación de estrategias de búsqueda:", "", "```text", formatear_comparacion(res), "```", ""]
        print(f"[{'OK' if ok else 'FALLA'}] Prueba {i}: {esc.nombre}")
    md += [f"**Total: {aprobados}/{len(ESCENARIOS)} pruebas aprobadas.**", ""]
    with open(args.salida, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n{aprobados}/{len(ESCENARIOS)} aprobadas. Reporte guardado en {args.salida}")


# ---------------------------------------------------------------------------
# Modo interactivo
# ---------------------------------------------------------------------------

def _pedir_estacion(red: RedTransporte, mensaje: str) -> str:
    while True:
        texto = input(mensaje).strip()
        try:
            return red.resolver_nombre(texto)
        except ValueError as e:
            print(f"  {e}")


def modo_interactivo() -> None:
    print("=" * 64)
    print("  Sistema experto de rutas TransMilenio (base de conocimiento + A*)")
    print("=" * 64)
    cerradas: List[str] = []
    while True:
        red = RedTransporte(cerradas=cerradas)
        print("\n1) Buscar ruta   2) Comparar algoritmos   3) Consultar base de conocimiento")
        print("4) Cerrar/abrir estación   5) Listar estaciones   0) Salir")
        opcion = input("Opción: ").strip()
        try:
            if opcion == "0":
                break
            if opcion in ("1", "2"):
                origen = _pedir_estacion(red, "Estación de origen: ")
                destino = _pedir_estacion(red, "Estación de destino: ")
                criterio = "transbordos" if input("¿Minimizar transbordos? (s/N): ").lower().startswith("s") else "tiempo"
                if opcion == "1":
                    print()
                    print(formatear_ruta(red, buscar_ruta(red, origen, destino, "a_estrella", criterio), detalle=True))
                else:
                    print()
                    print(formatear_comparacion([buscar_ruta(red, origen, destino, a, criterio) for a in ALGORITMOS]))
            elif opcion == "3":
                consulta = input("Consulta (ej. transbordo(E, T1, T2)): ")
                filas = red.kb.consultar(consulta)
                for f in filas[:30]:
                    print("  " + ", ".join(f"{k} = {formatear_termino(v)}" for k, v in f.items()) if f else "  Verdadero.")
                print(f"  {len(filas)} resultado(s)." if filas else "  Falso / sin resultados.")
            elif opcion == "4":
                est = _pedir_estacion(red, "Estación: ")
                if est in cerradas:
                    cerradas.remove(est)
                    print(f"  {est} vuelve a estar habilitada.")
                else:
                    cerradas.append(est)
                    print(f"  {est} marcada como cerrada: cerrada(\"{est}\") se agrega a la base de hechos.")
            elif opcion == "5":
                for e in red.estaciones:
                    print(f"  {e}  [{', '.join(red.troncales_de(e))}]")
        except (ValueError, ErrorLogico) as e:
            print(f"  Error: {e}")


# ---------------------------------------------------------------------------

def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ruta óptima en TransMilenio con base de conocimiento y búsqueda heurística")
    sub = p.add_subparsers(dest="comando")

    def opciones_red(sp):
        sp.add_argument("--cerrar", nargs="+", metavar="ESTACION", help="estaciones fuera de servicio")

    sp = sub.add_parser("ruta", help="calcula la mejor ruta entre dos estaciones")
    sp.add_argument("origen")
    sp.add_argument("destino")
    sp.add_argument("-a", "--algoritmo", choices=list(ALGORITMOS), default="a_estrella")
    sp.add_argument("-c", "--criterio", choices=list(ProblemaRuta.CRITERIOS), default="tiempo")
    sp.add_argument("-d", "--detalle", action="store_true", help="muestra todas las estaciones intermedias")
    opciones_red(sp)
    sp.set_defaults(func=cmd_ruta)

    sp = sub.add_parser("comparar", help="compara amplitud, costo uniforme, voraz y A*")
    sp.add_argument("origen")
    sp.add_argument("destino")
    sp.add_argument("-c", "--criterio", choices=list(ProblemaRuta.CRITERIOS), default="tiempo")
    opciones_red(sp)
    sp.set_defaults(func=cmd_comparar)

    sp = sub.add_parser("consultar", help='consulta lógica, ej. "transbordo(E, T1, T2)"')
    sp.add_argument("consulta")
    sp.add_argument("--limite", type=int, default=50)
    opciones_red(sp)
    sp.set_defaults(func=cmd_consultar)

    sp = sub.add_parser("explicar", help="muestra el árbol de prueba de un hecho, ej. transbordo Ricaurte E F")
    sp.add_argument("predicado")
    sp.add_argument("argumentos", nargs="*")
    opciones_red(sp)
    sp.set_defaults(func=cmd_explicar)

    sp = sub.add_parser("estaciones", help="lista las estaciones (o las de una troncal)")
    sp.add_argument("--troncal", help="código de troncal: A, B, D, E, F, J, K")
    sp.set_defaults(func=cmd_estaciones)

    sp = sub.add_parser("reglas", help="muestra las reglas y estadísticas de la inferencia")
    sp.set_defaults(func=cmd_reglas)

    sp = sub.add_parser("escenarios", help="ejecuta los escenarios de prueba y genera un reporte Markdown")
    sp.add_argument("--salida", default="resultados_pruebas.md")
    sp.set_defaults(func=cmd_escenarios)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    _utf8_en_consola()
    args = construir_parser().parse_args(argv)
    if not args.comando:
        modo_interactivo()
        return 0
    try:
        args.func(args)
        return 0
    except (ValueError, ErrorLogico) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
