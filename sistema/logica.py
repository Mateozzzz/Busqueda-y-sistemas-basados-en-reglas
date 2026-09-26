"""
Motor de inferencia lógico tipo Datalog (subconjunto de Prolog).

Representación del conocimiento
-------------------------------
    Hechos:     siguiente("Portal Norte", "Toberín", "B").
    Reglas:     tramo(A, B, T) :- siguiente(A, B, T).
    Negación:   habilitada(E) :- estacion(E), no cerrada(E).
    Integrado:  distinto(X, Y)

Las variables empiezan con mayúscula o con '_' (como en Prolog).
Las constantes son cadenas entre comillas ("..." o '...'), números
o identificadores en minúscula.

Razonamiento
------------
Encadenamiento hacia adelante (forward chaining): se aplican las reglas
sobre la base de hechos hasta alcanzar un punto fijo (no se derivan
hechos nuevos). La negación se evalúa por fallo (negation as failure),
lo que exige un programa estratificado: el motor calcula los estratos
automáticamente y evalúa cada uno en orden.

Cada hecho derivado guarda su justificación (regla + premisas), lo que
permite explicar "por qué" el sistema sabe algo.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import count
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union


class ErrorLogico(Exception):
    """Error de sintaxis o de semántica en la base de conocimiento."""


# ---------------------------------------------------------------------------
# Términos, literales y reglas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Var:
    nombre: str

    def __repr__(self) -> str:
        return self.nombre


Constante = Union[str, int, float]
Termino = Union[Var, str, int, float]
Hecho = Tuple[str, Tuple[Constante, ...]]
Premisa = Union[Hecho, str]  # un hecho, o texto para negaciones/integrados

PREDICADOS_INTEGRADOS = {
    "distinto": lambda a, b: a != b,
    "igual": lambda a, b: a == b,
}


def formatear_termino(t: Termino) -> str:
    if isinstance(t, Var):
        return t.nombre
    if isinstance(t, str):
        return '"' + t.replace('"', '\\"') + '"'
    return str(t)


def formatear_hecho(h: Hecho) -> str:
    pred, args = h
    return f"{pred}({', '.join(formatear_termino(a) for a in args)})"


@dataclass(frozen=True)
class Literal:
    predicado: str
    argumentos: Tuple[Termino, ...]
    negado: bool = False

    @property
    def es_integrado(self) -> bool:
        return self.predicado in PREDICADOS_INTEGRADOS

    def variables(self) -> Set[Var]:
        return {a for a in self.argumentos if isinstance(a, Var)}

    def __str__(self) -> str:
        args = ", ".join(formatear_termino(a) for a in self.argumentos)
        return f"{'no ' if self.negado else ''}{self.predicado}({args})"


@dataclass
class Regla:
    cabeza: Literal
    cuerpo: List[Literal]
    etiqueta: str = ""

    def __str__(self) -> str:
        return f"{self.cabeza} :- {', '.join(str(l) for l in self.cuerpo)}."

    def cuerpo_ordenado(self) -> List[Literal]:
        """Literales positivos primero; negaciones e integrados al final
        (cuando sus variables ya están ligadas)."""
        positivos = [l for l in self.cuerpo if not l.negado and not l.es_integrado]
        filtros = [l for l in self.cuerpo if l.negado or l.es_integrado]
        return positivos + filtros


# ---------------------------------------------------------------------------
# Analizador léxico y sintáctico
# ---------------------------------------------------------------------------

_TOKENS = re.compile(
    r"""
      (?P<espacio>\s+)
    | (?P<comentario>%[^\n]*)
    | (?P<cadena>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
    | (?P<numero>-?\d+(?:\.\d+)?)
    | (?P<implica>:-)
    | (?P<ident>[^\W\d]\w*)
    | (?P<simbolo>[(),.?])
    """,
    re.VERBOSE | re.UNICODE,
)


def _tokenizar(texto: str) -> List[Tuple[str, str, int]]:
    tokens, pos, linea = [], 0, 1
    while pos < len(texto):
        m = _TOKENS.match(texto, pos)
        if not m:
            raise ErrorLogico(f"Línea {linea}: carácter inesperado {texto[pos]!r}")
        tipo, valor = m.lastgroup, m.group()
        if tipo not in ("espacio", "comentario"):
            tokens.append((tipo, valor, linea))
        linea += valor.count("\n")
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, texto: str):
        self.tokens = _tokenizar(texto)
        self.i = 0
        self._anonimas = count(1)

    # utilidades --------------------------------------------------------
    def _ver(self) -> Optional[Tuple[str, str, int]]:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _tomar(self, valor: Optional[str] = None, tipo: Optional[str] = None):
        tok = self._ver()
        if tok is None:
            raise ErrorLogico(f"Fin de texto inesperado (se esperaba {valor or tipo})")
        if (valor and tok[1] != valor) or (tipo and tok[0] != tipo):
            raise ErrorLogico(f"Línea {tok[2]}: se esperaba {valor or tipo!r} y se encontró {tok[1]!r}")
        self.i += 1
        return tok

    # gramática -----------------------------------------------------------
    def programa(self) -> List[Tuple[Literal, List[Literal]]]:
        clausulas = []
        while self._ver() is not None:
            clausulas.append(self.clausula())
        return clausulas

    def clausula(self) -> Tuple[Literal, List[Literal]]:
        cabeza = self.literal()
        cuerpo: List[Literal] = []
        if self._ver() and self._ver()[1] == ":-":
            self._tomar(":-")
            cuerpo = self.conjuncion()
        self._tomar(".")
        return cabeza, cuerpo

    def conjuncion(self) -> List[Literal]:
        literales = [self.literal_cuerpo()]
        while self._ver() and self._ver()[1] == ",":
            self._tomar(",")
            literales.append(self.literal_cuerpo())
        return literales

    def literal_cuerpo(self) -> Literal:
        tok = self._ver()
        siguiente = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
        if tok and tok[1] == "no" and siguiente and siguiente[0] == "ident":
            self._tomar("no")
            lit = self.literal()
            return Literal(lit.predicado, lit.argumentos, negado=True)
        return self.literal()

    def literal(self) -> Literal:
        _, nombre, linea = self._tomar(tipo="ident")
        if nombre[0].isupper() or nombre[0] == "_":
            raise ErrorLogico(f"Línea {linea}: el predicado {nombre!r} debe iniciar en minúscula")
        args: List[Termino] = []
        if self._ver() and self._ver()[1] == "(":
            self._tomar("(")
            if self._ver() and self._ver()[1] != ")":
                args.append(self.termino())
                while self._ver() and self._ver()[1] == ",":
                    self._tomar(",")
                    args.append(self.termino())
            self._tomar(")")
        return Literal(nombre, tuple(args))

    def termino(self) -> Termino:
        tipo, valor, linea = self._tomar()
        if tipo == "cadena":
            return re.sub(r"\\(.)", r"\1", valor[1:-1])
        if tipo == "numero":
            return float(valor) if "." in valor else int(valor)
        if tipo == "ident":
            if valor == "_":
                return Var(f"_G{next(self._anonimas)}")
            if valor[0].isupper() or valor[0] == "_":
                return Var(valor)
            return valor  # átomo
        raise ErrorLogico(f"Línea {linea}: término inválido {valor!r}")


def parsear_programa(texto: str) -> List[Tuple[Literal, List[Literal]]]:
    return _Parser(texto).programa()


def parsear_consulta(texto: str) -> List[Literal]:
    """Convierte 'transbordo(E, T1, T2)' (o una conjunción) en literales."""
    texto = texto.strip()
    if not texto.endswith((".", "?")):
        texto += "."
    texto = texto[:-1] + "."
    p = _Parser(texto)
    literales = p.conjuncion()
    p._tomar(".")
    return literales


# ---------------------------------------------------------------------------
# Base de conocimiento y motor de inferencia
# ---------------------------------------------------------------------------

@dataclass
class EstadisticasInferencia:
    hechos_base: int = 0
    hechos_derivados: int = 0
    reglas: int = 0
    estratos: int = 0
    iteraciones: int = 0
    disparos: int = 0  # veces que una regla produjo un hecho nuevo


class BaseConocimiento:
    def __init__(self) -> None:
        self.hechos_base: Set[Hecho] = set()
        self.reglas: List[Regla] = []
        self._hechos: Dict[str, Set[Hecho]] = defaultdict(set)
        self._indice: Dict[str, Dict[Constante, Set[Hecho]]] = defaultdict(lambda: defaultdict(set))
        self._justificacion: Dict[Hecho, Tuple[str, Tuple[Premisa, ...]]] = {}
        self._saturada = False
        self.estadisticas = EstadisticasInferencia()

    # --- carga -----------------------------------------------------------
    def cargar_archivo(self, ruta: str) -> None:
        with open(ruta, encoding="utf-8") as f:
            try:
                self.cargar_texto(f.read())
            except ErrorLogico as e:
                raise ErrorLogico(f"{ruta}: {e}") from None

    def cargar_texto(self, texto: str) -> None:
        for cabeza, cuerpo in parsear_programa(texto):
            if cuerpo:
                self.agregar_regla(Regla(cabeza, cuerpo))
            else:
                if cabeza.variables():
                    raise ErrorLogico(f"El hecho {cabeza} contiene variables (debe ser fundamentado)")
                self.agregar_hecho(cabeza.predicado, *cabeza.argumentos)

    def agregar_hecho(self, predicado: str, *args: Constante) -> None:
        self.hechos_base.add((predicado, tuple(args)))
        self._saturada = False

    def retirar_hecho(self, predicado: str, *args: Constante) -> None:
        self.hechos_base.discard((predicado, tuple(args)))
        self._saturada = False

    def agregar_regla(self, regla: Regla) -> None:
        self._validar_regla(regla)
        regla.etiqueta = regla.etiqueta or f"R{len(self.reglas) + 1}"
        self.reglas.append(regla)
        self._saturada = False

    @staticmethod
    def _validar_regla(regla: Regla) -> None:
        """Regla segura: toda variable de la cabeza, de una negación o de un
        predicado integrado debe aparecer en un literal positivo del cuerpo."""
        ligadas: Set[Var] = set()
        for lit in regla.cuerpo:
            if not lit.negado and not lit.es_integrado:
                ligadas |= lit.variables()
        libres = regla.cabeza.variables() - ligadas
        for lit in regla.cuerpo:
            if lit.negado or lit.es_integrado:
                libres |= lit.variables() - ligadas
        if libres:
            nombres = ", ".join(sorted(v.nombre for v in libres))
            raise ErrorLogico(f"Regla insegura ({nombres} sin ligar): {regla}")

    # --- estratificación -----------------------------------------------
    def _estratificar(self) -> Dict[str, int]:
        predicados = {p for p, _ in self.hechos_base}
        for r in self.reglas:
            predicados.add(r.cabeza.predicado)
            predicados |= {l.predicado for l in r.cuerpo if not l.es_integrado}
        estrato = {p: 0 for p in predicados}
        limite = len(predicados)
        cambio = True
        while cambio:
            cambio = False
            for r in self.reglas:
                cabeza = r.cabeza.predicado
                for lit in r.cuerpo:
                    if lit.es_integrado:
                        continue
                    requerido = estrato[lit.predicado] + (1 if lit.negado else 0)
                    if estrato[cabeza] < requerido:
                        estrato[cabeza] = requerido
                        cambio = True
                        if estrato[cabeza] > limite:
                            raise ErrorLogico(
                                "Programa no estratificable: hay una negación dentro "
                                f"de un ciclo recursivo que involucra '{cabeza}'")
        return estrato

    # --- encadenamiento hacia adelante ------------------------------------
    def _registrar(self, hecho: Hecho) -> None:
        pred, args = hecho
        self._hechos[pred].add(hecho)
        if args:
            self._indice[pred][args[0]].add(hecho)

    def inferir(self) -> EstadisticasInferencia:
        self._hechos = defaultdict(set)
        self._indice = defaultdict(lambda: defaultdict(set))
        self._justificacion = {}
        for h in self.hechos_base:
            self._registrar(h)
            self._justificacion[h] = ("hecho", ())

        estrato = self._estratificar()
        por_nivel: Dict[int, List[Regla]] = defaultdict(list)
        for r in self.reglas:
            por_nivel[estrato[r.cabeza.predicado]].append(r)

        est = EstadisticasInferencia(hechos_base=len(self.hechos_base),
                                     reglas=len(self.reglas), estratos=len(por_nivel))
        for nivel in sorted(por_nivel):
            reglas = [(r, r.cuerpo_ordenado()) for r in por_nivel[nivel]]
            while True:  # punto fijo del estrato
                est.iteraciones += 1
                nuevos: Dict[Hecho, Tuple[str, Tuple[Premisa, ...]]] = {}
                for regla, cuerpo in reglas:
                    for sust, premisas in self._resolver(cuerpo, {}, ()):
                        args = tuple(sust[a] if isinstance(a, Var) else a
                                     for a in regla.cabeza.argumentos)
                        hecho = (regla.cabeza.predicado, args)
                        if hecho not in self._justificacion and hecho not in nuevos:
                            nuevos[hecho] = (regla.etiqueta, premisas)
                if not nuevos:
                    break
                for hecho, justif in nuevos.items():
                    self._registrar(hecho)
                    self._justificacion[hecho] = justif
                    est.disparos += 1

        est.hechos_derivados = len(self._justificacion) - len(self.hechos_base)
        self.estadisticas = est
        self._saturada = True
        return est

    def _candidatos(self, lit: Literal, sust: Dict[Var, Constante]):
        if lit.argumentos:
            primero = lit.argumentos[0]
            if isinstance(primero, Var):
                primero = sust.get(primero, primero)
            if not isinstance(primero, Var):
                return self._indice[lit.predicado].get(primero, ())
        return self._hechos.get(lit.predicado, ())

    @staticmethod
    def _unificar(args: Sequence[Termino], valores: Sequence[Constante],
                  sust: Dict[Var, Constante]) -> Optional[Dict[Var, Constante]]:
        if len(args) != len(valores):
            return None
        nueva = sust
        for t, v in zip(args, valores):
            if isinstance(t, Var):
                actual = nueva.get(t)
                if actual is None:
                    if nueva is sust:
                        nueva = dict(sust)
                    nueva[t] = v
                elif actual != v:
                    return None
            elif t != v:
                return None
        return nueva

    def _resolver(self, literales: Sequence[Literal], sust: Dict[Var, Constante],
                  premisas: Tuple[Premisa, ...]) -> Iterator[Tuple[Dict[Var, Constante], Tuple[Premisa, ...]]]:
        if not literales:
            yield sust, premisas
            return
        lit, resto = literales[0], literales[1:]
        if lit.es_integrado or lit.negado:
            valores = tuple(sust[a] if isinstance(a, Var) else a for a in lit.argumentos)
            if lit.es_integrado:
                cierto = PREDICADOS_INTEGRADOS[lit.predicado](*valores)
            else:
                cierto = (lit.predicado, valores) in self._hechos.get(lit.predicado, ())
            if cierto != lit.negado:
                texto = f"{'no ' if lit.negado else ''}{formatear_hecho((lit.predicado, valores))}"
                yield from self._resolver(resto, sust, premisas + (texto,))
            return
        # Orden determinista: la misma entrada produce siempre la misma salida
        for hecho in sorted(self._candidatos(lit, sust), key=repr):
            nueva = self._unificar(lit.argumentos, hecho[1], sust)
            if nueva is not None:
                yield from self._resolver(resto, nueva, premisas + (hecho,))

    # --- consultas ---------------------------------------------------------
    def _asegurar_saturada(self) -> None:
        if not self._saturada:
            self.inferir()

    def consultar(self, consulta: Union[str, List[Literal]]) -> List[Dict[str, Constante]]:
        """Consulta conjuntiva con variables. Devuelve las ligaduras encontradas."""
        self._asegurar_saturada()
        literales = parsear_consulta(consulta) if isinstance(consulta, str) else consulta
        ordenados = Regla(Literal("consulta", ()), list(literales)).cuerpo_ordenado()
        for lit in ordenados:
            if lit.negado or lit.es_integrado:
                ligadas = set().union(*(l.variables() for l in ordenados if not l.negado and not l.es_integrado))
                if lit.variables() - ligadas:
                    raise ErrorLogico(f"En la consulta, las variables de '{lit}' deben aparecer en un literal positivo")
        resultados, vistos = [], set()
        for sust, _ in self._resolver(ordenados, {}, ()):
            fila = {v.nombre: val for v, val in sust.items() if not v.nombre.startswith("_")}
            clave = tuple(sorted(fila.items(), key=lambda kv: kv[0]))
            if clave not in vistos:
                vistos.add(clave)
                resultados.append(fila)
        resultados.sort(key=lambda f: [str(v) for v in f.values()])
        return resultados

    def buscar(self, predicado: str, *patron: Optional[Constante]) -> Iterator[Tuple[Constante, ...]]:
        """Acceso rápido para el buscador: None actúa como comodín."""
        self._asegurar_saturada()
        if patron and patron[0] is not None:
            fuente = self._indice[predicado].get(patron[0], ())
        else:
            fuente = self._hechos.get(predicado, ())
        for _, args in sorted(fuente, key=repr):
            if len(args) == len(patron) and all(p is None or p == a for p, a in zip(patron, args)):
                yield args

    def es_cierto(self, predicado: str, *args: Constante) -> bool:
        self._asegurar_saturada()
        return (predicado, tuple(args)) in self._hechos.get(predicado, ())

    # --- explicación ---------------------------------------------------------
    def explicar(self, hecho: Hecho, profundidad_max: int = 8) -> str:
        """Árbol de prueba: qué regla derivó el hecho y a partir de qué premisas."""
        self._asegurar_saturada()
        if hecho not in self._justificacion:
            return f"{formatear_hecho(hecho)} NO se puede demostrar con la base de conocimiento actual."
        lineas: List[str] = []
        reglas_usadas: Dict[str, Regla] = {}
        por_etiqueta = {r.etiqueta: r for r in self.reglas}

        def recorrer(h: Premisa, prefijo: str, conector: str, nivel: int) -> None:
            if isinstance(h, str):  # negación o integrado
                lineas.append(f"{prefijo}{conector}{h}   [verificado]")
                return
            origen, premisas = self._justificacion[h]
            marca = "[hecho]" if origen == "hecho" else f"[regla {origen}]"
            lineas.append(f"{prefijo}{conector}{formatear_hecho(h)}   {marca}")
            if origen != "hecho":
                reglas_usadas[origen] = por_etiqueta[origen]
            if origen == "hecho" or nivel >= profundidad_max:
                return
            hijo_prefijo = prefijo + ("    " if conector.startswith("└") else "│   " if conector else "")
            for i, p in enumerate(premisas):
                ultimo = i == len(premisas) - 1
                recorrer(p, hijo_prefijo, "└── " if ultimo else "├── ", nivel + 1)

        recorrer(hecho, "", "", 0)
        if reglas_usadas:
            lineas.append("")
            lineas.append("Reglas aplicadas:")
            for etq in sorted(reglas_usadas, key=lambda e: int(e[1:]) if e[1:].isdigit() else 0):
                lineas.append(f"  {etq}: {reglas_usadas[etq]}")
        return "\n".join(lineas)
