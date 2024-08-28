import ifcopenshell

class IfcWallAnalyzer:
    def __init__(self, ifc_file_path, wall_guid):
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        self.wall_guid = wall_guid
        self.wall = self.ifc_file.by_guid(wall_guid)
        self.layer_details = []

    def analyze_wall(self):
        if not self.wall:
            print(f"Wall with GUID {self.wall_guid} not found.")
            return

        print("Name der Wand:", f"Wall {self.wall_guid}")
        self._get_relative_placement()
        self._get_product_definition_shape()

        # Ausgabe aller Layer-Details
        self._print_layer_details()

    def _get_relative_placement(self):
        # Funktion zum Abrufen und Anzeigen der relativen Platzierung
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
        # Funktion zum Abrufen und Verarbeiten der Produktdefinitionsform
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
                # Feststellen, ob "divers" nötig ist
                if representation_type is None:
                    representation_type = layer_info["RepresentationType"]
                elif representation_type != layer_info["RepresentationType"]:
                    diverse_representation = True

        if diverse_representation:
            representation_type = "divers"
        print("Representation Type der Wand:", representation_type)

    def _process_shape_aspect(self, aspect):
        # Funktion zur Verarbeitung eines einzelnen ShapeAspects
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
        return layer_info

    def _get_profile_points(self, profile):
        # Funktion zum Abrufen der Profilpunkte
        if profile.is_a('IFCARBITRARYCLOSEDPROFILEDEF'):
            if hasattr(profile, 'OuterCurve') and profile.OuterCurve.is_a('IFCINDEXEDPOLYCURVE'):
                indexed_polycurve = profile.OuterCurve
                if hasattr(indexed_polycurve, 'Points') and indexed_polycurve.Points.is_a('IFCCARTESIANPOINTLIST2D'):
                    point_list_2d = indexed_polycurve.Points
                    return point_list_2d.CoordList
        return None

    def _get_placement_details(self, position):
        # Funktion zum Abrufen von Location und RefDirection
        if position.is_a('IFCAXIS2PLACEMENT3D'):
            location = position.Location
            ref_direction = position.RefDirection
            return location.Coordinates, ref_direction.DirectionRatios if ref_direction else None
        return None, None

    def _print_layer_details(self):
        # Funktion zum Ausgeben der Layer-Details
        for index, layer in enumerate(self.layer_details):
            print(f"\nLayer {index + 1} Details:")
            print("Material:", layer.get("Material", "Nicht verfügbar"))
            print("Extrusionsstärke:", layer.get("Extrusionsstärke", "Nicht verfügbar"))
            print("Profilpunkte:", layer.get("Profilpunkte", "Nicht verfügbar"))
            print("Location:", layer.get("Location", "Nicht verfügbar"))
            print("RefDirection:", layer.get("RefDirection", "Nicht verfügbar"))
