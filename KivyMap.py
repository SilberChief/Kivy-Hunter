import os
import itertools
import random
import pytmx

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Rectangle
from kivy.logger import Logger
from kivy.properties import BooleanProperty, ListProperty
from kivy.uix.widget import Widget
from kivy.vector import Vector
from kivy.app import App
from kivy.config import Config

class KivyTiledMap(pytmx.TiledMap):


    def __init__(self, map_file_path=None, *args, **kwargs):
        assert map_file_path, 'tilemap.tmx'
        super(KivyTiledMap, self).__init__(map_file_path, *args, **kwargs)

        # Hole das Verzeichnis, das die Karten-Datei enthält
        self.map_dir = os.path.dirname(map_file_path)
        Logger.debug('KivyTiledMap: Verzeichnis der Karten-Datei: "{}"'.format(self.map_dir))

        # Lade die Kachelbilder für jedes Tileset
        for tileset in self.tilesets:
            self.loadTileImages(tileset)

    def loadTileImages(self, ts):
        """
        Lädt die Bilder im Dateinamen in Kivy-Bilder.
        """
        tile_image_path = os.path.join(self.map_dir, ts.source)
        assert os.path.exists(tile_image_path), f"Fehler: Tileset-Bild {tile_image_path} nicht gefunden!"
        texture = CoreImage(tile_image_path).texture

        ts.width, ts.height = texture.size
        tilewidth = ts.tilewidth + ts.spacing
        tileheight = ts.tileheight + ts.spacing
        Logger.debug('KivyTiledMap: Tileset: {}x{} mit {}x{} Kacheln'.format(ts.width, ts.height, tilewidth, tileheight))

        # Einige Tileset-Bilder sind möglicherweise etwas größer als der Kachelbereich
        width = int((((ts.width - ts.margin * 2 + ts.spacing) / tilewidth) * tilewidth) - ts.spacing)
        height = int((((ts.height - ts.margin * 2 + ts.spacing) / tileheight) * tileheight) - ts.spacing)
        Logger.debug('KivyTiledMap: Tileset: echte Größe: {}x{}'.format(width, height))

        # Initialisiere das Bild-Array
        self.images = [0] * self.maxgid

        p = itertools.product(
            range(ts.margin, height + ts.margin, tileheight),
            range(ts.margin, width + ts.margin, tilewidth)
        )

        for real_gid, (y, x) in enumerate(p, ts.firstgid):
            if x + ts.tilewidth - ts.spacing > width:
                continue

            gids = self.map_gid(real_gid)

            if gids:
                y = ts.height - y - ts.tileheight  # Invertiere y für OpenGL-Koordinaten

                tile = texture.get_region(x, y, ts.tilewidth, ts.tileheight)

                for gid, flags in gids:
                    self.images[gid] = tile

    def find_tile_with_property(self, property_name, layer_name='Meta'):
        layer = self.get_layer_by_name(layer_name)
        index = self.layers.index(layer)
        for tile in layer:
            properties = self.get_tile_properties(tile[0], tile[1], index)
            if properties and property_name in properties:
                return tile[0], tile[1]
        return None

    def tile_has_property(self, x, y, property_name, layer_name='Meta'):
        """Überprüft, ob die Kachelkoordinaten eine Kollision haben."""
        layer = self.get_layer_by_name(layer_name)
        layer_index = self.layers.index(layer)

        properties = self.get_tile_properties(x, y, layer_index)
        return property_name in properties if properties else False

    def valid_move(self, x, y):
        # Überprüft, ob die Kachel außerhalb der Grenzen liegt
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return False

        # Überprüft, ob die Kachel das Attribut 'Collidable' hat
        if self.tile_has_property(x, y, 'Collidable'):
            return False

        return True

    def get_adjacent_tiles(self, x, y):
        """Holt sich die benachbarten Kacheln (Nord, Süd, Ost, West) von x, y."""
        adjacent_tiles = []

        if self.valid_move(x, y - 1):
            adjacent_tiles.append((x, y - 1))

        if self.valid_move(x, y + 1):
            adjacent_tiles.append((x, y + 1))

        if self.valid_move(x - 1, y):
            adjacent_tiles.append((x - 1, y))

        if self.valid_move(x + 1, y):
            adjacent_tiles.append((x + 1, y))

        return adjacent_tiles


class TileMap(Widget):
    """Erstellt ein Kivy-Gitter und fügt die Kacheln der Map hinzu."""
    scaled_tile_size = ListProperty()

    def __init__(self, map_file_path=None, **kwargs):
        assert map_file_path
        self.tiled_map = KivyTiledMap(map_file_path)
        super(TileMap, self).__init__(**kwargs)

        self._scale = 1.0
        self.tile_map_size = (self.tiled_map.width, self.tiled_map.height)
        self.tile_size = (self.tiled_map.tilewidth, self.tiled_map.tileheight)
        self.scaled_tile_size = self.tile_size
        self.scaled_map_width = self.scaled_tile_size[0] * self.tile_map_size[0]
        self.scaled_map_height = self.scaled_tile_size[1] * self.tile_map_size[1]

    @property
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        self.scaled_tile_size = (self.tile_size[0] * self.scale, self.tile_size[1] * self.scale)
        self.scaled_map_width = self.scaled_tile_size[0] * self.tile_map_size[0]
        self.scaled_map_height = self.scaled_tile_size[1] * self.tile_map_size[1]
        self.on_size()

    def on_size(self, *args):
        Logger.debug('TileMap: Neu zeichnen')

        screen_tile_size = self.get_root_window().width / 8
        self.scaled_tile_size = (screen_tile_size, screen_tile_size)
        self.scaled_map_width = self.scaled_tile_size[0] * self.tile_map_size[0]
        self.scaled_map_height = self.scaled_tile_size[1] * self.tile_map_size[1]

        self.canvas.clear()
        with self.canvas:
            layer_idx = 0
            for layer in self.tiled_map.layers:
                if not layer.visible:
                    Logger.debug(f"Layer '{layer.name}' ist nicht sichtbar. Überspringe.")
                    continue

                Color(1.0, 1.0, 1.0, layer.opacity)

                for tile in layer:
                    tile_x, tile_y = tile[:2]
                    texture = self.tiled_map.get_tile_image(tile_x, tile_y, layer_idx)

                    if texture is None:
                        Logger.warning(f"Kein Texture für Tile ({tile_x}, {tile_y})")
                        continue

                    draw_pos = self._get_tile_pos(tile_x, tile_y)
                    draw_size = self.scaled_tile_size

                    Logger.debug(f"Zeichne Tile bei {draw_pos} mit Größe {draw_size}")
                    Rectangle(texture=texture, pos=draw_pos, size=draw_size)

                layer_idx += 1

    def _get_tile_pos(self, x, y):
        pos_x = x * self.scaled_tile_size[0]
        pos_y = (self.tile_map_size[1] - y - 1) * self.scaled_tile_size[1]
        return pos_x, pos_y

    def get_tile_position(self, x, y):
        return self._get_tile_pos(x, y)

    def get_tile_at_position(self, pos):
        pos = self.to_local(*pos)
        Logger.debug('TileMap: Finde Kachel bei Position {}'.format(pos))

        found_x = False
        tile_x = 0
        while tile_x < self.tiled_map.width:
            tile_x_right = (tile_x + 1) * self.scaled_tile_size[0]
            if tile_x_right < pos[0]:
                tile_x += 1
            else:
                found_x = True
                break

        tile_y = self.tiled_map.height
        while tile_y != 0:
            tile_y_top = (self.tiled_map.height - tile_y) * self.scaled_tile_size[1]
            if tile_y_top < pos[1]:
                tile_y -= 1
            else:
                if found_x:
                    return tile_x, tile_y
                break
        return None


from kivy.app import App

class TiledApp(App):
    def build(self):
        main_widget = Widget()
        map_file_path = 'tilemap.tmx'

        def add_widgets():
            Logger.debug('TiledApp: Erstelle TileMap mit Karten-Datei: {}'.format(map_file_path))
            tile_map = TileMap(map_file_path)
            main_widget.add_widget(tile_map)

        Clock.schedule_once(lambda *args: add_widgets())
        return main_widget

Config.set('kivy', 'log_level', 'debug')
if __name__ == '__main__':
    TiledApp().run()

    # Zeige die Version von pytmx an
    Logger.debug('TiledApp: pytmx Version: {}'.format(pytmx.__version__))


