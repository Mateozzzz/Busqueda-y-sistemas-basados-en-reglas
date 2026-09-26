"""Pruebas unitarias del motor de inferencia lógico."""
import unittest

from sistema.logica import BaseConocimiento, ErrorLogico, parsear_consulta


def kb_desde(texto: str) -> BaseConocimiento:
    kb = BaseConocimiento()
    kb.cargar_texto(texto)
    kb.inferir()
    return kb


class TestParser(unittest.TestCase):
    def test_hechos_reglas_y_comentarios(self):
        kb = kb_desde('''
            % comentario
            padre("Ana", "Luis").
            edad("Ana", 50).
            progenitor(X, Y) :- padre(X, Y).
        ''')
        self.assertEqual(len(kb.reglas), 1)
        self.assertTrue(kb.es_cierto("edad", "Ana", 50))
        self.assertTrue(kb.es_cierto("progenitor", "Ana", "Luis"))

    def test_cadenas_con_comillas_simples_y_tildes(self):
        kb = kb_desde("estacion('Av. Jiménez'). estacion(\"Héroes\").")
        self.assertTrue(kb.es_cierto("estacion", "Av. Jiménez"))
        self.assertTrue(kb.es_cierto("estacion", "Héroes"))

    def test_hecho_con_variables_es_error(self):
        with self.assertRaises(ErrorLogico):
            kb_desde("padre(X, \"Luis\").")

    def test_error_de_sintaxis_indica_linea(self):
        with self.assertRaises(ErrorLogico) as ctx:
            kb_desde('a("x").\nb("y"')
        self.assertIn("se esperaba", str(ctx.exception))

    def test_parsear_consulta_conjuntiva(self):
        lits = parsear_consulta("p(X), no q(X)")
        self.assertEqual(len(lits), 2)
        self.assertTrue(lits[1].negado)


class TestInferencia(unittest.TestCase):
    def test_encadenamiento_hacia_adelante_recursivo(self):
        kb = kb_desde('''
            padre("a", "b"). padre("b", "c"). padre("c", "d").
            ancestro(X, Y) :- padre(X, Y).
            ancestro(X, Z) :- padre(X, Y), ancestro(Y, Z).
        ''')
        self.assertTrue(kb.es_cierto("ancestro", "a", "d"))
        self.assertFalse(kb.es_cierto("ancestro", "d", "a"))
        self.assertEqual(len(kb.consultar("ancestro(X, Y)")), 6)

    def test_negacion_por_fallo(self):
        kb = kb_desde('''
            estacion("A"). estacion("B"). cerrada("B").
            habilitada(E) :- estacion(E), no cerrada(E).
        ''')
        self.assertTrue(kb.es_cierto("habilitada", "A"))
        self.assertFalse(kb.es_cierto("habilitada", "B"))

    def test_hecho_dinamico_cambia_conclusiones(self):
        kb = kb_desde('estacion("A"). habilitada(E) :- estacion(E), no cerrada(E).')
        self.assertTrue(kb.es_cierto("habilitada", "A"))
        kb.agregar_hecho("cerrada", "A")
        self.assertFalse(kb.es_cierto("habilitada", "A"))  # re-infiere automáticamente

    def test_predicado_integrado_distinto(self):
        kb = kb_desde('''
            linea("X", "1"). linea("X", "2").
            transbordo(E, A, B) :- linea(E, A), linea(E, B), distinto(A, B).
        ''')
        self.assertEqual(len(kb.consultar("transbordo(E, A, B)")), 2)
        self.assertFalse(kb.es_cierto("transbordo", "X", "1", "1"))

    def test_regla_insegura_es_rechazada(self):
        with self.assertRaises(ErrorLogico):
            kb_desde("p(X, Y) :- q(X).")
        with self.assertRaises(ErrorLogico):
            kb_desde("p(X) :- q(X), no r(Y).")

    def test_programa_no_estratificable(self):
        with self.assertRaises(ErrorLogico):
            kb_desde('n("a"). p(X) :- n(X), no q(X). q(X) :- n(X), no p(X).')

    def test_consulta_con_constantes(self):
        kb = kb_desde('padre("a", "b"). padre("a", "c").')
        self.assertEqual(kb.consultar('padre("a", H)'), [{"H": "b"}, {"H": "c"}])
        self.assertEqual(kb.consultar('padre("a", "b")'), [{}])  # verdadero, sin variables
        self.assertEqual(kb.consultar('padre("z", H)'), [])

    def test_explicacion_muestra_regla_y_premisas(self):
        kb = kb_desde('padre("a", "b"). progenitor(X, Y) :- padre(X, Y).')
        texto = kb.explicar(("progenitor", ("a", "b")))
        self.assertIn("regla R1", texto)
        self.assertIn('padre("a", "b")', texto)
        self.assertIn("NO se puede demostrar", kb.explicar(("progenitor", ("b", "a"))))


if __name__ == "__main__":
    unittest.main()
