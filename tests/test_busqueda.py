"""Pruebas de integración: base de conocimiento de TransMilenio + búsqueda."""
import unittest

from sistema.busqueda import ProblemaRuta, a_estrella, buscar_ruta, costo_uniforme
from sistema.red import RedTransporte


class TestRed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.red = RedTransporte()

    def test_todas_las_estaciones_tienen_coordenadas(self):
        self.assertGreater(len(self.red.estaciones), 80)
        for e in self.red.estaciones:
            self.assertIn(e, self.red.coordenadas)

    def test_transbordos_inferidos_por_las_reglas(self):
        kb = self.red.kb
        self.assertTrue(kb.es_cierto("transbordo", "Ricaurte", "E", "F"))
        self.assertTrue(kb.es_cierto("transbordo", "Av. Jiménez", "A", "J"))
        self.assertTrue(kb.es_cierto("transbordo", "Calle 100", "B", "E"))
        self.assertFalse(kb.es_cierto("transbordo", "Calle 45", "A", "B"))

    def test_tramos_bidireccionales(self):
        kb = self.red.kb
        self.assertTrue(kb.es_cierto("movimiento", "Toberín", "Portal Norte", "B"))
        self.assertTrue(kb.es_cierto("movimiento", "Portal Norte", "Toberín", "B"))

    def test_resolver_nombre_sin_tildes(self):
        self.assertEqual(self.red.resolver_nombre("heroes"), "Héroes")
        self.assertEqual(self.red.resolver_nombre("AV JIMENEZ"), "Av. Jiménez")
        with self.assertRaises(ValueError):
            self.red.resolver_nombre("calle")        # ambiguo
        with self.assertRaises(ValueError):
            self.red.resolver_nombre("Estación X")   # inexistente


class TestBusqueda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.red = RedTransporte()

    def test_misma_troncal_sin_transbordos(self):
        r = buscar_ruta(self.red, "Portal Norte", "Calle 100")
        self.assertTrue(r.encontrado)
        self.assertEqual(r.transbordos, 0)
        self.assertEqual(r.paradas, 11)

    def test_a_estrella_es_optimo(self):
        """A* debe encontrar el mismo costo que costo uniforme (Dijkstra)."""
        pares = [("Portal Norte", "Portal Américas"), ("Portal 80", "Universidades"),
                 ("Portal El Dorado", "Calle 72"), ("Tercer Milenio", "Toberín")]
        for o, d in pares:
            with self.subTest(o=o, d=d):
                p = ProblemaRuta(self.red, o, d)
                self.assertAlmostEqual(a_estrella(p).costo, costo_uniforme(p).costo, places=6)

    def test_a_estrella_expande_menos_nodos(self):
        p = ProblemaRuta(self.red, "Portal 80", "Portal Américas")
        self.assertLess(a_estrella(p).nodos_expandidos, costo_uniforme(p).nodos_expandidos)

    def test_heuristica_admisible(self):
        """h(n) nunca sobreestima el costo real hasta el destino."""
        for destino in ("Portal Américas", "Universidades", "Toberín"):
            for est in self.red.estaciones:
                real = costo_uniforme(ProblemaRuta(self.red, est, destino)).costo
                with self.subTest(est=est, destino=destino):
                    self.assertLessEqual(self.red.heuristica(est, destino), real + 1e-9)

    def test_voraz_puede_ser_suboptima(self):
        voraz = buscar_ruta(self.red, "Escuela Militar", "U. Nacional", "voraz")
        estrella = buscar_ruta(self.red, "Escuela Militar", "U. Nacional", "a_estrella")
        self.assertGreater(voraz.minutos, estrella.minutos)

    def test_conexion_peatonal(self):
        r = buscar_ruta(self.red, "Portal El Dorado", "Museo del Oro")
        self.assertIn("caminar", [p.accion for p in r.pasos])

    def test_estacion_cerrada_obliga_a_replanificar(self):
        normal = buscar_ruta(self.red, "Portal Norte", "Ricaurte")
        self.assertIn("Paloquemao", normal.estaciones_ruta)
        red_cerrada = RedTransporte(cerradas=["Paloquemao"])
        desvio = buscar_ruta(red_cerrada, "Portal Norte", "Ricaurte")
        self.assertTrue(desvio.encontrado)
        self.assertNotIn("Paloquemao", desvio.estaciones_ruta)
        self.assertGreaterEqual(desvio.costo, normal.costo)

    def test_sin_ruta(self):
        red = RedTransporte(cerradas=["Toberín"])
        self.assertFalse(buscar_ruta(red, "Portal Norte", "Calle 100").encontrado)

    def test_origen_o_destino_cerrado_es_error(self):
        red = RedTransporte(cerradas=["Calle 100"])
        with self.assertRaises(ValueError):
            buscar_ruta(red, "Calle 100", "Portal Norte")

    def test_origen_igual_destino(self):
        r = buscar_ruta(self.red, "Calle 45", "Calle 45")
        self.assertTrue(r.encontrado)
        self.assertEqual(r.pasos, [])

    def test_criterio_transbordos_no_aumenta_transbordos(self):
        for o, d in [("Portal Norte", "Portal Américas"), ("Portal 80", "Museo del Oro")]:
            t = buscar_ruta(self.red, o, d, criterio="tiempo")
            m = buscar_ruta(self.red, o, d, criterio="transbordos")
            self.assertLessEqual(m.transbordos, t.transbordos)


if __name__ == "__main__":
    unittest.main()
