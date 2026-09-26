"""
Capa de dominio: conecta la base de conocimiento lógica con el buscador.

- Carga hechos y reglas desde /conocimiento.
- Agrega hechos dinámicos (estaciones cerradas) antes de inferir.
- Calcula costos de los tramos y la heurística a partir de las coordenadas.
"""
from __future__ import annotations

import difflib
import math
import os
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

from .logica import BaseConocimiento, ErrorLogico

DIR_CONOCIMIENTO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conocimiento")


def normalizar(texto: str) -> str:
    """'Av. Jiménez' -> 'av jimenez' (sin tildes, mayúsculas ni signos)."""
    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    limpio = "".join(c if c.isalnum() else " " for c in sin_tildes.lower())
    return " ".join(limpio.split())


def distancia_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Distancia en línea recta (fórmula de Haversine)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


class RedTransporte:
    def __init__(self, cerradas: Iterable[str] = (), dir_conocimiento: str = DIR_CONOCIMIENTO):
        self.kb = BaseConocimiento()
        self.kb.cargar_archivo(os.path.join(dir_conocimiento, "hechos.kb"))
        self.kb.cargar_archivo(os.path.join(dir_conocimiento, "reglas.kb"))
        self.kb.inferir()  # primera pasada para conocer las estaciones

        self.estaciones: List[str] = sorted(str(e) for (e,) in self.kb.buscar("estacion", None))
        self._por_nombre: Dict[str, str] = {normalizar(e): e for e in self.estaciones}

        # Hechos dinámicos: estaciones cerradas -> se vuelve a inferir
        self.cerradas: List[str] = []
        for nombre in cerradas:
            est = self.resolver_nombre(nombre)
            self.kb.agregar_hecho("cerrada", est)
            self.cerradas.append(est)
        self.estadisticas = self.kb.inferir()

        self.troncales: Dict[str, str] = {str(c): str(n) for c, n in self.kb.buscar("troncal", None, None)}
        self.coordenadas: Dict[str, Tuple[float, float]] = {
            str(e): (float(la), float(lo)) for e, la, lo in self.kb.buscar("coordenadas", None, None, None)}
        sin_coord = [e for e in self.estaciones if e not in self.coordenadas]
        if sin_coord:
            raise ErrorLogico("Faltan coordenadas para: " + ", ".join(sin_coord))

        params = {str(n): float(v) for n, v in self.kb.buscar("parametro", None, None)}
        self.velocidad_kmh = params.get("velocidad_comercial_kmh", 25.0)
        self.parada_min = params.get("tiempo_parada_min", 0.5)
        self.transbordo_min = params.get("tiempo_transbordo_min", 5.0)

    # --- nombres ----------------------------------------------------------------
    def resolver_nombre(self, texto: str) -> str:
        """Acepta nombres sin tildes, en minúscula o incompletos si no son ambiguos."""
        clave = normalizar(texto)
        if clave in self._por_nombre:
            return self._por_nombre[clave]
        candidatos = [e for k, e in self._por_nombre.items() if k.startswith(clave)] or \
                     [e for k, e in self._por_nombre.items() if clave and clave in k]
        if len(candidatos) == 1:
            return candidatos[0]
        if len(candidatos) > 1:
            raise ValueError(f"'{texto}' es ambiguo. ¿Quiso decir: {', '.join(sorted(candidatos))}?")
        parecidos = difflib.get_close_matches(clave, list(self._por_nombre), n=3, cutoff=0.5)
        sugerencia = f" ¿Quiso decir: {', '.join(self._por_nombre[p] for p in parecidos)}?" if parecidos else ""
        raise ValueError(f"No existe la estación '{texto}'.{sugerencia}")

    def nombre_troncal(self, codigo: Optional[str]) -> str:
        return f"{codigo} ({self.troncales.get(codigo, '?')})" if codigo else "-"

    def troncales_de(self, estacion: str) -> List[str]:
        return sorted(str(t) for (_, t) in self.kb.buscar("pertenece", estacion, None))

    def esta_habilitada(self, estacion: str) -> bool:
        return self.kb.es_cierto("habilitada", estacion)

    # --- costos y heurística --------------------------------------------------------
    def minutos_directos(self, a: str, b: str) -> float:
        """Tiempo en línea recta a velocidad comercial (sin paradas)."""
        return distancia_km(self.coordenadas[a], self.coordenadas[b]) / self.velocidad_kmh * 60

    def tiempo_tramo(self, a: str, b: str) -> float:
        return self.minutos_directos(a, b) + self.parada_min

    def heuristica(self, estacion: str, destino: str) -> float:
        """h(n): minutos para ir en línea recta a velocidad comercial.
        Es ADMISIBLE porque ningún recorrido real es más corto que la línea recta
        y cada tramo cuesta al menos distancia/velocidad; y es CONSISTENTE por la
        desigualdad triangular."""
        return self.minutos_directos(estacion, destino)
