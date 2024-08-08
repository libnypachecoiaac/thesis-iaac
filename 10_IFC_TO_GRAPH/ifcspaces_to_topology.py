import ifcopenshell
from topologicpy.Vertex import Vertex
from topologicpy.Face import Face
from topologicpy.Cell import Cell
from topologicpy.Cluster import Cluster
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
import math

def get_translation_vector(placement):
    """Extract the translation vector from the IfcAxis2Placement3D."""
    if placement and placement.Location:
        location = placement.Location
        return location.Coordinates[0], location.Coordinates[1], location.Coordinates[2]
    return 0.0, 0.0, 0.0

def get_direction_vector(ifc_file, direction):
    """Extract the direction vector from the IfcDirection."""
    if direction:
        dir_ref = ifc_file[direction.id()]
        if dir_ref:
            return tuple(dir_ref.DirectionRatios)  # Ensure the returned vector is a tuple
    return (0.0, 0.0, 1.0)  # Default direction

def get_axis_vector(placement):
    """Extract the axis vector from the IfcAxis2Placement3D."""
    if placement and placement.Axis:
        return tuple(placement.Axis.DirectionRatios)
    return (0.0, 0.0, 1.0)  # Default axis

def rotate_point(x, y, angle):
    """Rotate a point around the origin (0, 0) by a given angle in degrees."""
    radians = math.radians(angle)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    new_x = x * cos_angle - y * sin_angle
    new_y = x * sin_angle + y * cos_angle
    return new_x, new_y

def rotate_point_around_x(x, y, z, angle):
    """Rotate a point around the x-axis by a given angle in degrees."""
    radians = math.radians(angle)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    new_y = y * cos_angle - z * sin_angle
    new_z = y * sin_angle + z * cos_angle
    return x, new_y, new_z

def apply_transformation(coordinates, translation_vector, axis_vector, ref_direction_vector):
    """Apply translation and rotation to the coordinates."""
    transformed_coordinates = []

    for point in coordinates:
        x, y = point
        z = 0.0  # Since the original coordinates are 2D

        if axis_vector == (0.0, 0.0, -1.0):
            x, y, z = rotate_point_around_x(x, y, z, 180)  # Rotate 180 degrees around x-axis
        if ref_direction_vector == (0.0, 1.0, 0.0):
            x, y = rotate_point(x, y, 90)  # Rotate 90 degrees
        elif ref_direction_vector == (-1.0, 0.0, 0.0):
            x, y = rotate_point(x, y, 180)  # Rotate 180 degrees
        elif ref_direction_vector == (0.0, -1.0, 0.0):
            x, y = rotate_point(x, y, 270)  # Rotate 270 degrees
        
        # Apply translation
        new_x = x + translation_vector[0]
        new_y = y + translation_vector[1]
        new_z = z + translation_vector[2]
        transformed_coordinates.append((new_x, new_y, new_z))

    return transformed_coordinates

def extract_face_from_space(space, ifc_file):
    """Extract face from the given space."""
    representation = space.Representation
    if representation:
        shape = representation.Representations[0]
        if shape and shape.Items:
            for item in shape.Items:
                if item.is_a("IfcExtrudedAreaSolid"):
                    profile = item.SweptArea
                    if profile and profile.is_a("IfcArbitraryClosedProfileDef"):
                        curve = profile.OuterCurve
                        if curve and curve.is_a("IfcIndexedPolyCurve"):
                            point_list = curve.Points
                            if point_list and point_list.is_a("IfcCartesianPointList2D"):
                                coordinates = point_list.CoordList
                                translation_vector = get_translation_vector(item.Position)
                                axis_vector = get_axis_vector(item.Position)
                                ref_direction_vector = get_direction_vector(ifc_file, item.Position.RefDirection)
                                if coordinates:
                                    transformed_coordinates = apply_transformation(coordinates, translation_vector, axis_vector, ref_direction_vector)
                                    # Convert coordinates to Vertex objects
                                    vertices = [Vertex.ByCoordinates(x, y, z) for x, y, z in transformed_coordinates]
                                    # Create a Face from the vertices
                                    face = Face.ByVertices(vertices)
                                    return face
    return None

def main(ifc_file, spaces_in_storey):

    # List to hold all faces and their corresponding space names
    faces_and_names = []

    # Loop through each filtered IfcSpace and extract face
    for index, space in enumerate(spaces_in_storey, start=1):
        print(f"Generating Face {index}/{len(spaces_in_storey)}")
        face = extract_face_from_space(space, ifc_file)
        if face:
            faces_and_names.append((face, space.GlobalId))
        else:
            print(f"Could not generate face for space {index}.")

    # List to hold all cells
    cells = []

    # Create cells from faces and assign dictionaries
    for face, name in faces_and_names:
        cell = Cell.ByThickenedFace(face, thickness=1500, bothSides=True)
        cell_dict = Dictionary.ByKeyValue("Name", name)
        cell.SetDictionary(cell_dict)
        cells.append(cell)

    # Create a complex from all cells
    building = Cluster.ByTopologies(cells)

    # Self-merge the complex
    building = Topology.SelfMerge(building)

    return building

if __name__ == "__main__":
    main()