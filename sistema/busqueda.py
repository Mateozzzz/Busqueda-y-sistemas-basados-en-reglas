"""
Formulación del problema como búsqueda en un espacio de estados.

Estado:     (estación, troncal en la que viaja el usuario)
            troncal = None  -> aún no ha abordado (estado inicial)
            troncal = A_PIE -> acaba de llegar caminando a otra estación
Acciones:   abordar, viajar (a la estación vecina), transbordo, caminar.
            Las acciones posibles NO están programadas en Python: se obtienen
            consultando los hechos derivados por la base de conocimiento
            (puede_abordar/2, movimiento/3, transbordo/3, caminata/3).
Meta:       estar en la estación destino (con cualquier troncal).
Costo:      minutos estimados (criterio "tiempo") o transbordos y luego
            minutos (criterio "transbordos").
"""
from __future__ import annotations

import heapq
import itertools
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from .red import RedTransporte

A_PIE = "a pie"
PENALIZACION_TRANSBORDO = 1000.0  # para el criterio "transbordos"


@dataclass(frozen=True)
class Estado:
    estacion: str
    troncal: Optional[str]


@dataclass(frozen=True)
class Paso:
    accion: str            # abordar | viajar | transbordo | caminar
    desde: str
    hacia: str
    troncal: Optional[str]
    minutos: float


@dataclass
class Resultado:
    algoritmo: str
    origen: str
    destino: str
    criterio: str
    encontrado: bool
    pasos: List[Paso] = field(default_factory=list)
    costo: float = 0.0
    nodos_expandidos: int = 0
    nodos_generados: int = 0
    max_frontera: int = 0
    tiempo_ms: float = 0.0

    @property
    def minutos(self) -> float:
        return sum(p.minutos for p in self.pasos)

    @property
    def transbordos(self) -> int:
        return sum(1 for p in self.pasos
                   if p.accion == "transbordo" or (p.accion == "abordar" and p.minutos > 0))

    @property
    def paradas(self) -> int:
        return sum(1 for p in self.pasos if p.accion == "viajar")

    @property
    def estaciones_ruta(self) -> List[str]:
        ruta = [self.origen]
        for p in self.pasos:
            if p.hacia != ruta[-1]:
                ruta.append(p.hacia)
        return ruta


class ProblemaRuta:
    CRITERIOS = ("tiempo", "transbordos")

    def __init__(self, red: RedTransporte, origen: str, destino: str, criterio: str = "tiempo"):
        if criterio not in self.CRITERIOS:
            raise ValueError(f"Criterio inválido: {criterio}. Opciones: {', '.join(self.CRITERIOS)}")
        self.red = red
        self.origen = red.resolver_nombre(origen)
        self.destino = red.resolver_nombre(destino)
        self.criterio = criterio
        for est in (self.origen, self.destino):
            if not red.esta_habilitada(est):
                raise ValueError(f"La estación '{est}' está cerrada.")
        self.inicial = Estado(self.origen, None)

    def es_meta(self, s: Estado) -> bool:
        return s.estacion == self.destino

    def h(self, s: Estado) -> float:
        return self.red.heuristica(s.estacion, self.destino)

    def _costo(self, minutos: float, es_transbordo: bool) -> float:
        extra = PENALIZACION_TRANSBORDO if (es_transbordo and self.criterio == "transbordos") else 0.0
        return minutos + extra

    def sucesores(self, s: Estado) -> Iterator[Tuple[Paso, Estado, float]]:
        kb, red, e, t = self.red.kb, self.red, s.estacion, s.troncal
        if t is None or t == A_PIE:
            # R8: puede_abordar(E, T)
            espera = 0.0 if t is None else red.transbordo_min
            for _, troncal in kb.buscar("puede_abordar", e, None):
                yield (Paso("abordar", e, e, troncal, espera), Estado(e, troncal),
                       self._costo(espera, t == A_PIE))
        else:
            # R7: movimiento(A, B, T)
            for _, vecina, _ in kb.buscar("movimiento", e, None, t):
                m = red.tiempo_tramo(e, vecina)
                yield Paso("viajar", e, vecina, t, m), Estado(vecina, t), self._costo(m, False)
            # R9: transbordo(E, T1, T2)
            for _, _, t2 in kb.buscar("transbordo", e, t, None):
                m = red.transbordo_min
                yield Paso("transbordo", e, e, t2, m), Estado(e, t2), self._costo(m, True)
        # R10/R11: caminata(A, B, Minutos)
        if t != A_PIE:
            for _, destino, minutos in kb.buscar("caminata", e, None, None):
                m = float(minutos)
                yield Paso("caminar", e, destino, None, m), Estado(destino, A_PIE), self._costo(m, False)


# ---------------------------------------------------------------------------
# Algoritmos
# ---------------------------------------------------------------------------

def _reconstruir(padre: Dict[Estado, Tuple[Optional[Estado], Optional[Paso]]], meta: Estado) -> List[Paso]:
    pasos: List[Paso] = []
    s: Optional[Estado] = meta
    while s is not None:
        anterior, paso = padre[s]
        if paso is not None:
            pasos.append(paso)
        s = anterior
    return list(reversed(pasos))


def _nuevo_resultado(nombre: str, p: ProblemaRuta) -> Resultado:
    return Resultado(nombre, p.origen, p.destino, p.criterio, encontrado=False)


def busqueda_amplitud(p: ProblemaRuta) -> Resultado:
    """Búsqueda no informada: minimiza el número de ACCIONES, no el tiempo."""
    r = _nuevo_resultado("amplitud", p)
    t0 = time.perf_counter()
    padre: Dict[Estado, Tuple[Optional[Estado], Optional[Paso]]] = {p.inicial: (None, None)}
    g: Dict[Estado, float] = {p.inicial: 0.0}
    frontera = deque([p.inicial])
    r.nodos_generados = 1
    meta = p.inicial if p.es_meta(p.inicial) else None
    while frontera and meta is None:
        s = frontera.popleft()
        r.nodos_expandidos += 1
        for paso, s2, costo in p.sucesores(s):
            r.nodos_generados += 1
            if s2 not in padre:
                padre[s2] = (s, paso)
                g[s2] = g[s] + costo
                if p.es_meta(s2):
                    meta = s2
                    break
                frontera.append(s2)
        r.max_frontera = max(r.max_frontera, len(frontera))
    r.tiempo_ms = (time.perf_counter() - t0) * 1000
    if meta is not None:
        r.encontrado, r.pasos, r.costo = True, _reconstruir(padre, meta), g[meta]
    return r


def _primero_el_mejor(p: ProblemaRuta, nombre: str,
                      prioridad: Callable[[float, Estado], float]) -> Resultado:
    """Búsqueda en grafo con cola de prioridad. f(n) la define 'prioridad'."""
    r = _nuevo_resultado(nombre, p)
    t0 = time.perf_counter()
    g: Dict[Estado, float] = {p.inicial: 0.0}
    padre: Dict[Estado, Tuple[Optional[Estado], Optional[Paso]]] = {p.inicial: (None, None)}
    desempate = itertools.count()
    frontera = [(prioridad(0.0, p.inicial), next(desempate), p.inicial)]
    cerrados = set()
    r.nodos_generados = 1
    while frontera:
        _, _, s = heapq.heappop(frontera)
        if s in cerrados:
            continue  # entrada obsoleta de la cola
        if p.es_meta(s):  # prueba de meta al EXPANDIR -> garantiza optimalidad
            r.encontrado, r.pasos, r.costo = True, _reconstruir(padre, s), g[s]
            break
        cerrados.add(s)
        r.nodos_expandidos += 1
        for paso, s2, costo in p.sucesores(s):
            r.nodos_generados += 1
            if s2 in cerrados:
                continue
            nuevo_g = g[s] + costo
            if nuevo_g < g.get(s2, float("inf")):
                g[s2] = nuevo_g
                padre[s2] = (s, paso)
                heapq.heappush(frontera, (prioridad(nuevo_g, s2), next(desempate), s2))
        r.max_frontera = max(r.max_frontera, len(frontera))
    r.tiempo_ms = (time.perf_counter() - t0) * 1000
    return r


def costo_uniforme(p: ProblemaRuta) -> Resultado:
    """f(n) = g(n). Óptima, pero no usa información del destino (Dijkstra)."""
    return _primero_el_mejor(p, "costo_uniforme", lambda g, s: g)


def voraz(p: ProblemaRuta) -> Resultado:
    """f(n) = h(n). Rápida, pero NO garantiza la mejor ruta."""
    return _primero_el_mejor(p, "voraz", lambda g, s: p.h(s))


def a_estrella(p: ProblemaRuta) -> Resultado:
    """f(n) = g(n) + h(n). Óptima con heurística admisible y consistente."""
    return _primero_el_mejor(p, "a_estrella", lambda g, s: g + p.h(s))


ALGORITMOS: Dict[str, Callable[[ProblemaRuta], Resultado]] = {
    "a_estrella": a_estrella,
    "costo_uniforme": costo_uniforme,
    "voraz": voraz,
    "amplitud": busqueda_amplitud,
}


def buscar_ruta(red: RedTransporte, origen: str, destino: str,
                algoritmo: str = "a_estrella", criterio: str = "tiempo") -> Resultado:
    if algoritmo not in ALGORITMOS:
        raise ValueError(f"Algoritmo inválido: {algoritmo}. Opciones: {', '.join(ALGORITMOS)}")
    return ALGORITMOS[algoritmo](ProblemaRuta(red, origen, destino, criterio))
