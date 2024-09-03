import ifcopenshell
import numpy as np
from ifcopenshell.util import placement
from topologicpy.Face import Face
from topologicpy.Cell import Cell
from topologicpy.Dictionary import Dictionary
from topologicpy.Topology import Topology
from topologicpy.CellComplex import CellComplex
from topologicpy.Vertex import Vertex

class IfcWallAnalyzer:
    def __init__(self, ifc_file_path, wall_guid):
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        self.wall_guid = wall_guid
        self.wall = self.ifc_file.by_guid(wall_guid)
        self.layer_details = []
        self.cells = []  # Liste, um die erzeugten Cells zu speichern

    def analyze_wall(self):
        if not self.wall:
            print(f"Wall with GUID {self.wall_guid} not found.")
            return

        print("Name der Wand:", f"Wall {self.wall_guid}")
        self._get_relative_placement()
        self._get_product_definition_shape()

        # Erzeuge CellComplex aus den gesammelten Cells
        wall_cell_complex = self._create_cell_complex()
        print("CellComplex erstellt.")
        
        # Ausgabe aller Layer-Details
        self._print_layer_details()

        return wall_cell_complex

    def _get_relative_placement(self):
        if self.wall.ObjectPlacement and self.wall.ObjectPlacement.RelativePlacement:
            relative_placement = self.wall.ObjectPlacement.RelativePlacement
            if relative_placement.is_a('IFCAXIS2PLACEMENT3D'):
                location = relative_placement.Location
                ref_direction = relative_placement.RefDirection
                print("Relative Placement Location:", location.Coordinates)
                if ref_direction:
                    print("Relative Placement RefDirection:", ref_direction.DirectionRatios)
                else:
                    print("Relative Placement RefDirection: None")

    def _get_product_definition_shape(self):
        product_definition_shape = self.wall.Representation
        if not product_definition_shape:
            print("Keine Repräsentation gefunden.")
            return

        representation_type = None
        diverse_representation = False

        if hasattr(product_definition_shape, 'HasShapeAspects'):
            for aspect in product_definition_shape.HasShapeAspects:
                layer_info = self._process_shape_aspect(aspect)
                self.layer_details.append(layer_info)
                if representation_type is None:
                    representation_type = layer_info["RepresentationType"]
                elif representation_type != layer_info["RepresentationType"]:
                    diverse_representation = True

        if diverse_representation:
            representation_type = "divers"
        print("Representation Type der Wand:", representation_type)

    def _process_shape_aspect(self, aspect):
        layer_info = {"Material": aspect.Name}

        for representation in aspect.ShapeRepresentations:
            if representation.is_a('IFCSHAPEREPRESENTATION'):
                for item in representation.Items:
                    if item.is_a('IFCEXTRUDEDAREASOLID'):
                        # Abrufen der Details
                        layer_info["Extrusionsstärke"] = item.Depth
                        profile = item.SweptArea
                        layer_info["RepresentationType"] = "ArbitraryClosedProfil" if profile.is_a('IFCARBITRARYCLOSEDPROFILEDEF') else "divers"
                        layer_info["Profilpunkte"] = self._get_profile_points(profile)
                        layer_info["Location"], layer_info["RefDirection"] = self._get_placement_details(item.Position)
                        
                        # Berechnung der absoluten Koordinaten
                        absolute_points = self._calculate_absolute_coordinates(item, layer_info["Profilpunkte"])
                        layer_info["AbsoluteKoordinaten"] = absolute_points

                        # Erstelle die Geometrie in Topologic
                        self._create_topologic_geometry(layer_info)

        return layer_info

    def _get_profile_points(self, profile):
        if profile.is_a('IFCARBITRARYCLOSEDPROFILEDEF'):
            if hasattr(profile, 'OuterCurve') and profile.OuterCurve.is_a('IFCINDEXEDPOLYCURVE'):
                indexed_polycurve = profile.OuterCurve
                if hasattr(indexed_polycurve, 'Points') and indexed_polycurve.Points.is_a('IFCCARTESIANPOINTLIST2D'):
                    point_list_2d = indexed_polycurve.Points
                    return point_list_2d.CoordList
        return None

    def _get_placement_details(self, position):
        if position.is_a('IFCAXIS2PLACEMENT3D'):
            location = position.Location
            ref_direction = position.RefDirection
            return location.Coordinates, ref_direction.DirectionRatios if ref_direction else None
        return None, None

    def _calculate_absolute_coordinates(self, extruded_area_solid, profile_points):
        if not profile_points:
            print("Keine Profilpunkte vorhanden.")
            return None

        # Berechnung der Rotationsmatrix basierend auf RefDirection
        ref_direction = extruded_area_solid.Position.RefDirection.DirectionRatios if extruded_area_solid.Position.RefDirection else (1.0, 0.0, 0.0)
        rotation_angle = self._determine_rotation_angle(ref_direction)
        rotation_matrix = self._rotation_matrix_z(rotation_angle)

        # Berechnung der Translationsmatrix basierend auf der Profilposition
        profile_location = extruded_area_solid.Position.Location.Coordinates
        translation_matrix = np.identity(4)
        translation_matrix[0:3, 3] = profile_location

        # Berechnung der absoluten Platzierung der Wand
        wall_absolute_placement = self._calculate_absolute_placement(self.wall.ObjectPlacement)

        absolute_points = []
        for point in profile_points:
            point_homogeneous = np.array([point[0], point[1], 0.0, 1.0])
            rotated_point = np.dot(rotation_matrix, point_homogeneous)
            translated_point = np.dot(translation_matrix, rotated_point)
            absolute_point = np.dot(wall_absolute_placement, translated_point)
            absolute_points.append(absolute_point[:3])

        return absolute_points

    def _determine_rotation_angle(self, ref_direction):
        if ref_direction == (1, 0, 0):
            return 0
        elif ref_direction == (0, 1, 0):
            return 90
        elif ref_direction == (-1, 0, 0):
            return 180
        elif ref_direction == (0, -1, 0):
            return 270
        else:
            return 0  # Standardfall

    def _rotation_matrix_z(self, angle_degrees):
        angle_radians = np.radians(angle_degrees)
        cos_a = np.cos(angle_radians)
        sin_a = np.sin(angle_radians)
        return np.array([
            [cos_a, -sin_a, 0, 0],
            [sin_a, cos_a, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])

    def _calculate_absolute_placement(self, local_placement):
        if not local_placement:
            print("Keine lokale Platzierung gefunden.")
            return np.identity(4)

        total_matrix = placement.get_local_placement(local_placement)
        
        # Navigiere durch die Hierarchie der Platzierungen
        while local_placement.PlacementRelTo:
            local_placement = local_placement.PlacementRelTo
            parent_matrix = placement.get_local_placement(local_placement)
            total_matrix = np.dot(parent_matrix, total_matrix)
        
        return total_matrix

    def _create_topologic_geometry(self, layer_info):
        # Erstelle Vertices aus den absoluten Koordinaten
        vertices = [Vertex.Point(x=point[0], y=point[1], z=point[2]) for point in layer_info["AbsoluteKoordinaten"]]

        # Erstelle ein Face aus den Vertices
        face = Face.ByVertices(vertices)

        # Erstelle eine Cell aus dem Face mit der angegebenen Extrusionsstärke
        cell = Cell.ByThickenedFace(face, thickness=layer_info["Extrusionsstärke"], bothSides=False)

        # Erstelle ein Dictionary für das Material
        material_dict = Dictionary.ByKeyValue("Material", layer_info["Material"])

        # Füge das Dictionary zur Cell hinzu
        cell_with_dict = Topology.AddDictionary(cell, material_dict)

        # Füge die Cell der Liste hinzu
        self.cells.append(cell_with_dict)

    def _create_cell_complex(self):
        # Erzeuge ein CellComplex aus den erzeugten Cells
        if not self.cells:
            print("Keine Zellen vorhanden.")
            return None
        cell_complex = CellComplex.ByCells(self.cells, transferDictionaries=True)
        return cell_complex

    def _print_layer_details(self):
        for index, layer in enumerate(self.layer_details):
            print(f"\nLayer {index + 1} Details:")
            print("Material:", layer.get("Material", "Nicht verfügbar"))
            print("Extrusionsstärke:", layer.get("Extrusionsstärke", "Nicht verfügbar"))
            print("Profilpunkte:", layer.get("Profilpunkte", "Nicht verfügbar"))
            print("Location:", layer.get("Location", "Nicht verfügbar"))
            print("RefDirection:", layer.get("RefDirection", "Nicht verfügbar"))
            print("Absolute Koordinaten:", layer.get("AbsoluteKoordinaten", "Nicht verfügbar"))