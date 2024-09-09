import ifcopenshell
import ifcopenshell.geom
import numpy as np
import logging
import yaml
import re
import csv
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Face import Face
from topologicpy.Cell import Cell

def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

def filter_spaces_by_name(spaces):
    # For 0301
    # if True:
    #     exclude_pattern = re.compile(r'(-10$|^Area:)')
    #     filtered_spaces = []
        
    #     for space in spaces:
    #         if not exclude_pattern.search(space.Name):
    #             filtered_spaces.append(space)
    #     return filtered_spaces

    # For HUS28
    # digit_pattern = re.compile(r'^\d{1,5}$')
    # filtered_spaces = []
    # for space in spaces:
    #     if digit_pattern.match(space.Name):
    #         filtered_spaces.append(space)
    # return filtered_spaces

    # For 3501
    exclude_pattern = re.compile(r'^Area:|[-]')
    filtered_spaces = []
    for space in spaces:
        if not exclude_pattern.search(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces


def get_guids_of_spaces(spaces):
    guids = []
    for space in spaces:
        guids.append(space.GlobalId)
    return guids

def create_rotation_matrix(axis, ref_direction):
    
    # Convert axis and reference direction to numpy arrays
    axis = np.array(axis)
    ref_dir = np.array(ref_direction)
    
    # Normalize the axis vector to ensure it has a unit length (necessary?)
    axis = axis / np.linalg.norm(axis)
    
    # Adjust ref_dir to be orthogonal to axis and normalize it
    ref_dir = ref_dir - np.dot(ref_dir, axis) * axis
    ref_dir = ref_dir / np.linalg.norm(ref_dir)
    
    # Calculate the local Y-axis as the cross product of the axis (Z-axis) and ref_dir (X-axis)
    local_y_axis = np.cross(axis, ref_dir)

    # Construct the rotation matrix using orthogonal vectors as columns
    rotation_matrix = np.array([
        ref_dir,         # local X-axis
        local_y_axis,    # local Y-axis
        axis             # local Z-axis
    ]).T  # Transpose to align vectors as columns

    return rotation_matrix

def rotation_matrix_to_axis_angle(R):

    # Calculate the angle of rotation
    angle = np.arccos((np.trace(R) - 1) / 2)
    angle_degrees = np.degrees(angle)

    # Calculate the rotation axis
    rx = R[2, 1] - R[1, 2]
    ry = R[0, 2] - R[2, 0]
    rz = R[1, 0] - R[0, 1]
    axis = np.array([rx, ry, rz])
    
    # Normalize the axis if it's not the zero vector
    if np.linalg.norm(axis) != 0:
        axis = axis / np.linalg.norm(axis)
    else:
        # Return a zero vector if axis calculation results in zero vector
        axis = np.array([0.0, 0.0, 0.0])

    return axis, angle_degrees

def scale_topology_to_meters(topology):
    # Skaliert die gesamte Topologie von Millimetern zu Metern
    scaled_topology = Topology.Scale(topology, origin=(0, 0, 0), x=0.001, y=0.001, z=0.001)
    return scaled_topology





# Setup logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

# Load config.yaml
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

ifc_file_path = config["ifc_file"]
storey_name = config["storey_name"]

# Load IFC
ifc_file = ifcopenshell.open(ifc_file_path)

# Load Spaces from IFC
ifc_spaces = ifc_file.by_type("IfcSpace")
print(f"Amount of all IfcSpaces: {len(ifc_spaces)} ")

# Filter Spaces by storey
ifc_spaces = filter_ifcspaces_by_storey(ifc_spaces, storey_name)
print(f"Amount of IfcSpaces in specified storey'{storey_name}': {len(ifc_spaces)}")

# Further filter spaces by names containing only digits (1-5 digits)
ifc_spaces = filter_spaces_by_name(ifc_spaces)
print(f"Number of IfcSpaces with valid names: {len(ifc_spaces)}")

# Get GUIDs of filtered IfcSpaces
ifc_space_guids = get_guids_of_spaces(ifc_spaces)

if len(ifc_spaces) != len(ifc_space_guids):
    print("!! GUIDs dont match Spaces !!")


topo_spaces = []
dic_spaces = {}

for index, (space, guid) in enumerate(zip(ifc_spaces, ifc_space_guids), start=1):
    print(f"Reconstructin Space: {index}/{len(ifc_spaces)}, Space Name: {space.Name}, GUID: {guid}")

    ### Gather Informations of Space

    # Get local placement of the space
    local_placement = space.ObjectPlacement
    axis_placement = local_placement.RelativePlacement

    # Extract coordinates for space's relative placement
    if isinstance(axis_placement.Location, ifcopenshell.entity_instance):
        space_rel_placement = axis_placement.Location.Coordinates
    else:
        raise ValueError("No valid IFC Cartesian Point found in the space's placement.")

    # Determine axis and reference direction, with defaults for Z and X axes if not specified
    space_rel_axis = axis_placement.Axis.DirectionRatios if axis_placement.Axis else (0.0, 0.0, 1.0)  # Default to Z-axis
    space_rel_ref_direction = axis_placement.RefDirection.DirectionRatios if axis_placement.RefDirection else (1.0, 0.0, 0.0)  # Default to X-axis

    logging.debug(f"Relative Placement of IfcSpace: {space_rel_placement}")
    logging.debug(f"Axis (Z-axis): {space_rel_axis}")
    logging.debug(f"RefDirection (X-axis): {space_rel_ref_direction}")

    # Retrieve the product definition shape of the space (which contains geometric representations)
    product_definition_shape = space.Representation
    logging.debug("IFCPRODUCTDEFINITIONSHAPE found: %s", product_definition_shape)

    if product_definition_shape:
        # Iterate over the representations (e.g., Body, Footprint, etc.)
        for representation in product_definition_shape.Representations:
            if representation.is_a('IfcShapeRepresentation'):
                logging.debug(f"Found Shape Representation: {representation.RepresentationType}")

                # Iterate through items in the shape representation
                for item in representation.Items:
                    if item.is_a('IfcExtrudedAreaSolid'):
                        # Get extrusion depth of the space
                        space_extrusion_depth = item.Depth
                        logging.debug(f"Extrusion Depth: {space_extrusion_depth}")

                        # Get location, axis, and reference direction of the extrusion
                        if item.Position.is_a('IfcAxis2Placement3D'):
                            space_axis_placement = item.Position
                            space_location = space_axis_placement.Location
                            space_ref_direction = space_axis_placement.RefDirection.DirectionRatios if space_axis_placement.RefDirection else (1.0, 0.0, 0.0)
                            space_axis_direction = space_axis_placement.Axis.DirectionRatios if space_axis_placement.Axis else (0.0, 0.0, 1.0)

                            logging.debug(f"Location (IFCCARTESIANPOINT): {space_location.Coordinates}")
                            logging.debug(f"Axis (IFCDIRECTION): {space_axis_direction}")
                            logging.debug(f"RefDirection (IFCDIRECTION): {space_ref_direction}")

                        else:
                            logging.debug("No valid IFCAXIS2PLACEMENT3D found for space.")

                        # Get extrusion direction
                        space_extruded_direction = item.ExtrudedDirection.DirectionRatios
                        logging.debug(f"Extruded Direction (IFCDIRECTION): {space_extruded_direction}")

                        # Get the profile definition type and handle specific profile types
                        profile = item.SweptArea
                        profile_type = profile.is_a()
                        logging.debug(f"Profile Type: {profile_type}")

                        if profile_type == 'IfcArbitraryClosedProfileDef':
                            # Retrieve points for the outer curve of the profile
                            if hasattr(profile, 'OuterCurve') and profile.OuterCurve.is_a('IfcIndexedPolyCurve'):
                                indexed_polycurve = profile.OuterCurve
                                if hasattr(indexed_polycurve, 'Points') and indexed_polycurve.Points.is_a('IfcCartesianPointList2D'):
                                    point_list_2d = indexed_polycurve.Points
                                    points = point_list_2d.CoordList

                                    logging.debug("----VERTICES----")
                                    for point in points:
                                        logging.debug(f"Point: {point}")
                        else:
                            logging.debug(f"Profile type {profile_type} not supported or not handled.")
                    else:
                        logging.debug("Item is not IFCEXTRUDEDAREASOLID")
            else:
                logging.debug("Representation is not an IfcShapeRepresentation")


    ### Align Element in Local CoordSystem

    # Apply the rotation matrix
    rotation_matrix = create_rotation_matrix(space_axis_direction, space_ref_direction)

    # Ensure points are rotated and translated 
    local_points = []
    for point in points:
        point_3d = np.array([point[0], point[1], 0.0])  # Embed 2D point into 3D
        rotated_point = rotation_matrix.dot(point_3d)   # Apply the rotation matrix
        translated_point = rotated_point + space_location.Coordinates  # Translate based on layer location
        local_points.append(translated_point)

    # Transform Extrusion Direction
    extruded_direction_vector = np.array(space_extruded_direction)
    transformed_extruded_direction = np.dot(rotation_matrix, extruded_direction_vector)

    logging.debug("Calculated local points after rotation and translation:")
    for p in local_points:
        logging.debug(p)

    logging.debug("Transformierter Extrusionsvektor:")
    logging.debug(transformed_extruded_direction)



    ### Build Topology

    # Convert the calculated points to vertices
    vertices = [Vertex.ByCoordinates(x, y, z) for x, y, z in local_points]

    # Create a face using the vertices
    face = Face.ByVertices(vertices)
    face_normal = Face.Normal(face)

    # Output to confirm the face and its normal vector have been created
    logging.debug(face)
    logging.debug(face_normal)

    # Normalize the face normal and extrusion direction to ensure correct dot product calculation
    face_normal = face_normal / np.linalg.norm(face_normal)
    extrusion_direction = np.array(transformed_extruded_direction)
    extrusion_direction = extrusion_direction / np.linalg.norm(extrusion_direction)

    # Calculate the dot product between the face normal and the extrusion direction
    dot_product = np.dot(face_normal, extrusion_direction)

    # Determine if the face extrusion needs to be reversed based on the dot product
    # Adjustment of threshold to handle floating-point precision issues
    reverse = dot_product < -0.9999

    logging.debug("Face Normal: %s", face_normal)
    logging.debug("Extrusion Direction: %s", extrusion_direction)
    logging.debug("Dot Product: %s", dot_product)
    logging.debug("Reverse: %s", reverse)

    # Create cell by extruding the face with specified thickness
    cell = Cell.ByThickenedFace(face, thickness=space_extrusion_depth, bothSides=False, reverse=reverse)

    # Output to confirm that the cell has been created
    logging.debug("Cell created: %s", cell)

    ### Transformation from local CoordSystem to ProjectCoordSystem

    rotation_matrix = create_rotation_matrix(space_rel_axis, space_rel_ref_direction)
    axis, angle = rotation_matrix_to_axis_angle(rotation_matrix)

    # Test if Vector is Null
    if np.allclose(axis, [0, 0, 0]) and np.isclose(angle, 0):
        # No Rotation needed
        logging.debug("Keine Rotation erforderlich.")
        rotated_topology = cell  # No changes
    elif np.allclose(axis, [0, 0, 0]) and np.isclose(angle, 180):
        # Special Case "Mirroring"
        logging.debug("Sonderfall 180-Grad-Rotation erkannt.")
        rotation_axis = [0, 0, 1]  # Define a axis
        rotation_angle = 180  # 

        # Rotate
        rotated_topology = Topology.Rotate(
            cell,
            Vertex.ByCoordinates(0, 0, 0),
            rotation_axis,
            rotation_angle
        )
    else:
        # Standard Case
        rotation_axis = axis.tolist()
        rotation_angle = angle

        # Rotate
        rotated_topology = Topology.Rotate(
            cell,
            Vertex.ByCoordinates(0, 0, 0),
            rotation_axis,
            rotation_angle
        )

    # Translate rotated topology to the wall's relative placement
    final_topology = Topology.Translate(
        rotated_topology, 
        x=space_rel_placement[0], 
        y=space_rel_placement[1], 
        z=space_rel_placement[2]
    )

    final_topology = [scale_topology_to_meters(final_topology)]

    # Output the transformed topology to verify the translation
    logging.debug("Transformed Topology: %s", final_topology)

    dic_spaces[guid] = final_topology

print("-- Reconstruction of Spaces DONE --")

print("-- Checking for Adjacency of Rooms now --")


touching_cells = {}

def cells_share_face(cell1, cell2):
    # Merge the cells into the same CellComplex structure
    merged = Topology.Merge(topologyA=cell1, topologyB=cell2)
    # Get the merged cells from the merged topology
    merged_cells = Topology.Cells(merged)
    # Check if they share any faces
    shared_faces = Topology.SharedFaces(merged_cells[0], merged_cells[1])
    return len(shared_faces) > 0

guids = list(dic_spaces.keys())  # List of all GUIDs
for i, guid1 in enumerate(guids):
    print(f"Check {i+1} / {len(dic_spaces.keys())}")
    cell1 = dic_spaces[guid1][0] 
    touching = []
    for j, guid2 in enumerate(guids):
        if i != j:
            cell2 = dic_spaces[guid2][0]
            # Check if the two cells share any faces
            if cells_share_face(cell1, cell2):
                touching.append(guid2)  # Add the GUID of the touching room
    if touching:
        touching_cells[guid1] = touching

# Prepare the data for CSV output
csv_data = []
for cell_name, touch_cell_names in touching_cells.items():
    if cell_name not in touch_cell_names:
        touching_guids = ",".join(touch_cell_names)
        row = [cell_name, touching_guids]
        csv_data.append(row)

# Write the data to a CSV file
with open('Output01_RoomToRoom_BySeparationLine.csv', mode='w', newline='') as file:
    writer = csv.writer(file, delimiter=';')
    for row in csv_data:
        writer.writerow(row)

print("-- Data has been written to Output01_RoomToRoom_BySeparationLine.csv --")