import ifcopenshell
import ifcopenshell.geom
import logging
import yaml
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Face import Face
from topologicpy.Cell import Cell
from topologicpy.Dictionary import Dictionary
from topologicpy.Cluster import Cluster
from topologicpy.CellComplex import CellComplex
import numpy as np
import csv

def find_touching_walls(topology1, topology2):
    cells1 = Topology.Cells(topology1)
    cells2 = Topology.Cells(topology2)

    for index1, cell1 in enumerate(cells1):
        for index2, cell2 in enumerate(cells2):
            try:
                # Attempt to merge the cells
                merged_cell = Topology.Merge(cell1, cell2)
                
                # Get the cells in the merged topology
                merged_cells = Topology.Cells(merged_cell)

                # Ensure that merged_cells contains at least two cells
                if len(merged_cells) < 2:
                    print("Merged cells have less than 2 elements.")
                    continue

                shared_faces = Topology.SharedFaces(merged_cells[0], merged_cells[1])

                if shared_faces:
                    return True
                
            except RuntimeError as e:
                # Catch and print any RuntimeErrors from the merge operation
                print(f"Failed to merge topologies: {e}")
                print(f"Cell1: {cell1}, Cell2: {cell2}")
                continue

    return False

def get_ifc_guid(topo):
    topo_dict = Topology.Dictionary(topo)
    print(topo_dict)
    text = Dictionary.ValueAtKey(topo_dict, "guid")
    print(text)
    return text

def find_ifc_storey(ifc_file, storey_name):
    target_storey = None
    for storey in ifc_file.by_type("IfcBuildingStorey"):
        if storey.Name == storey_name:
            target_storey = storey
            break

    if not target_storey:
        print(f"Storey with name '{storey_name}' was not found.")
    else:
        print(f"Storey '{storey_name}' found. OID: {target_storey.id()}")
        return target_storey

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

def extract_geometry_info_from_shape_aspect(shape_aspect):
    coordinates_list = []
    indices_list = []
    voids_indices_list = []

    # Überprüfen, ob die ShapeAspect eine IfcPolygonalFaceSet enthält
    for representation in shape_aspect.ShapeRepresentations:
        if representation.is_a('IfcShapeRepresentation'):
            for item in representation.Items:
                if item.is_a('IfcPolygonalFaceSet'):
                    # IFCCARTESIANPOINTLIST3D (Koordinaten) extrahieren
                    if hasattr(item, 'Coordinates'):
                        coordinates = item.Coordinates.CoordList
                        coordinates_list.extend(coordinates)
                        print("  IFCCARTESIANPOINTLIST3D (Koordinaten):")
                        for coord in coordinates:
                            print(f"    - {coord}")

                    # IFCINDEXEDPOLYGONALFACE (Flächen) und Voids extrahieren
                    if hasattr(item, 'Faces'):
                        faces = item.Faces
                        print("  IFCINDEXEDPOLYGONALFACE (Flächen):")
                        for face in faces:
                            if face.is_a('IfcIndexedPolygonalFaceWithVoids'):
                                indices_list.append(face.CoordIndex)
                                voids_indices_list.extend(face.InnerCoordIndices)
                                print(f"    - Outer: {face.CoordIndex}, Voids: {face.InnerCoordIndices}")
                            else:
                                indices_list.append(face.CoordIndex)
                                print(f"    - {face.CoordIndex}")
    return coordinates_list, indices_list, voids_indices_list

def clean_indices_list(indices_list, voids_indices_list):
    cleaned_indices_list = []

    for indices in indices_list:
        if not any(index in [void_index for void_tup in voids_indices_list for void_index in void_tup] for index in indices):
            cleaned_indices_list.append(indices)

    return cleaned_indices_list

# Setup logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

# Load config.yaml
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

ifc_file_path = config["ifc_file"]
storey_name = config["storey_name"]

# Load IFC
ifc_file = ifcopenshell.open(ifc_file_path)

# Find corresponding IfcBuildingStorey
ifc_storey = find_ifc_storey(ifc_file, storey_name)

wall_guids = []

# Iterate all IfcWalls
for wall in ifc_file.by_type("IfcWall"):
    if wall.ContainedInStructure:
        for rel in wall.ContainedInStructure:
            # Check if Wall is in TargetStorey
            if rel.RelatingStructure == ifc_storey:
                wall_guids.append(wall.GlobalId)

print("GUIDs von Wänden in Plan:", wall_guids)
print(len(wall_guids))

dic_walls = {}
topo_walls = []

for wall_guid in wall_guids:
    print("IFC GUID of Wall:", wall_guid)
    wall = ifc_file.by_guid(wall_guid)

    ### Gather Informations of Wall

    # Get local placement of the wall
    local_placement = wall.ObjectPlacement
    axis_placement = local_placement.RelativePlacement

    # Extract coordinates for wall's relative placement
    if isinstance(axis_placement.Location, ifcopenshell.entity_instance):
        wall_rel_placement = axis_placement.Location.Coordinates
    else:
        raise ValueError("No valid IFC Cartesian Point found in the wall's placement.")

    # Determine axis and reference direction, with defaults for Z and X axes if not specified
    wall_axis = axis_placement.Axis.DirectionRatios if axis_placement.Axis else (0.0, 0.0, 1.0)  # Default to Z-axis
    wall_ref_direction = axis_placement.RefDirection.DirectionRatios if axis_placement.RefDirection else (1.0, 0.0, 0.0)  # Default to X-axis

    print(f"Relative Placement of IfcWall: {wall_rel_placement}")
    print(f"Axis (Z-axis): {wall_axis}")
    print(f"RefDirection (X-axis): {wall_ref_direction}")

    ### Gather Informations of Layers

    # Retrieve the product definition shape of wall (which contains geometric representations)
    product_definition_shape = wall.Representation
    print("IFCPRODUCTDEFINITIONSHAPE found:", product_definition_shape)

    shape_aspects = []

    # Check if the product definition shape has any shape aspects
    if product_definition_shape and hasattr(product_definition_shape, 'HasShapeAspects'):
        shape_aspects = product_definition_shape.HasShapeAspects
        if shape_aspects:
            print(f"Found {len(shape_aspects)} Shape Aspects")
        else:
            print("HasShapeAspects exists but is empty.")
    else:
        print("No IFCSHAPEASPECTs found or 'HasShapeAspects' does not exist.")

    cells = []

    for shape_aspect in shape_aspects:
    
        ### Gather Informations of specific Layer

        material = shape_aspect.Name

        for representation in shape_aspect.ShapeRepresentations:
            if representation.is_a('IFCSHAPEREPRESENTATION'):
                # Iterate through items in the shape representation
                for item in representation.Items:
                    if item.is_a('IFCEXTRUDEDAREASOLID'):
                        # Get extrusion depth of the layer
                        layer_extrusion_depth = item.Depth

                        # Get location, axis, and reference direction of the extrusion
                        if item.Position.is_a('IFCAXIS2PLACEMENT3D'):
                            layer_axis_placement = item.Position
                            layer_location = layer_axis_placement.Location
                            layer_ref_direction = layer_axis_placement.RefDirection.DirectionRatios if layer_axis_placement.RefDirection else (1.0, 0.0, 0.0)
                            layer_axis_direction = layer_axis_placement.Axis.DirectionRatios if layer_axis_placement.Axis else (0.0, 0.0, 1.0)
                        else:
                            print("No valid IFCAXIS2PLACEMENT3D found.")

                        # Get extrusion direction
                        layer_extruded_direction = item.ExtrudedDirection.DirectionRatios

                        # Get the profile definition type and handle specific profile types
                        profile = item.SweptArea
                        layer_profile_type = profile.is_a()
                        print(f"Profile Type: {layer_profile_type}")

                        if layer_profile_type == 'IfcArbitraryClosedProfileDef':
                            # Retrieve points for the outer curve of the profile
                            if hasattr(profile, 'OuterCurve') and profile.OuterCurve.is_a('IFCINDEXEDPOLYCURVE'):
                                indexed_polycurve = profile.OuterCurve
                                if hasattr(indexed_polycurve, 'Points') and indexed_polycurve.Points.is_a('IFCCARTESIANPOINTLIST2D'):
                                    point_list_2d = indexed_polycurve.Points
                                    points = point_list_2d.CoordList

                        elif layer_profile_type == 'IfcArbitraryProfileDefWithVoids':
                            # Retrieve points for the outer curve when profile has voids
                            # Here "InnerCurve" is neglected because, our Goal can be achieved without these Openings
                            if hasattr(profile, 'OuterCurve') and profile.OuterCurve.is_a('IFCINDEXEDPOLYCURVE'):
                                indexed_polycurve = profile.OuterCurve
                                if hasattr(indexed_polycurve, 'Points') and indexed_polycurve.Points.is_a('IFCCARTESIANPOINTLIST2D'):
                                    point_list_2d = indexed_polycurve.Points
                                    points = point_list_2d.CoordList
                            else:
                                print("No valid OuterCurve or Points found for IFCARBITRARYPROFILEDEFWITHVOIDS")
                        else:
                            print("Profile definition is neither IfcArbitraryClosedProfileDef nor IfcArbitraryProfileDefWithVoids")
                    
                        # Output wall  details
                        #print("----WALL----")
                        #print("Location (IFCCARTESIANPOINT):", wall_rel_placement)
                        #print("Axis (IFCDIRECTION):", wall_axis)
                        #print("RefDirection (IFCCARTESIANPOINT):", wall_ref_direction)

                        #print("----LAYER----")
                        #print("Extrusion Depth:", layer_extrusion_depth)
                        #print("Material", material)
                        #print("Location (IFCCARTESIANPOINT):", layer_location.Coordinates)
                        #print("Axis (IFCDIRECTION):", layer_axis_direction)
                        #print("RefDirection (IFCDIRECTION):", layer_ref_direction) 
                        #print("Extruded Direction (IFCDIRECTION):", layer_extruded_direction)

                        # Output the coordinates of the vertices defining the profile
                        #print("----VERTICES----")
                        #for point in points:
                        #    print(point)

                        ### Align Element in Local CoordSystem

                        # Apply the rotation matrix
                        rotation_matrix = create_rotation_matrix(layer_axis_direction, layer_ref_direction)

                        # Ensure points are rotated and translated 
                        local_points = []
                        for point in points:
                            point_3d = np.array([point[0], point[1], 0.0])  # Embed 2D point into 3D
                            rotated_point = rotation_matrix.dot(point_3d)   # Apply the rotation matrix
                            translated_point = rotated_point + layer_location.Coordinates  # Translate based on layer location
                            local_points.append(translated_point)

                        # Transform Extrusion Direction
                        extruded_direction_vector = np.array(layer_extruded_direction)
                        transformed_extruded_direction = np.dot(rotation_matrix, extruded_direction_vector)

                        #print("Calculated local points after rotation and translation:")
                        #for p in local_points:
                        #    print(p)

                        #print("Transformierter Extrusionsvektor:")
                        #print(transformed_extruded_direction)

                        ### Build Topology

                        # Convert the calculated points to vertices
                        vertices = [Vertex.ByCoordinates(x, y, z) for x, y, z in local_points]

                        # Create a face using the vertices
                        face = Face.ByVertices(vertices)
                        face_normal = Face.Normal(face)

                        # Output to confirm the face and its normal vector have been created
                        #print(face)
                        #print(face_normal)

                        # Normalize the face normal and extrusion direction to ensure correct dot product calculation
                        face_normal = face_normal / np.linalg.norm(face_normal)
                        extrusion_direction = np.array(transformed_extruded_direction)
                        extrusion_direction = extrusion_direction / np.linalg.norm(extrusion_direction)

                        # Calculate the dot product between the face normal and the extrusion direction
                        dot_product = np.dot(face_normal, extrusion_direction)

                        # Determine if the face extrusion needs to be reversed based on the dot product
                        # Adjustment of threshold to handle floating-point precision issues
                        reverse = dot_product < -0.9999

                        #print("Face Normal:", face_normal)
                        #print("Extrusion Direction:", extrusion_direction)
                        #print("Dot Product:", dot_product)
                        #print("Reverse:", reverse)

                        # Create cell by extruding the face with specified thickness
                        cell = Cell.ByThickenedFace(face, thickness=layer_extrusion_depth, bothSides=False, reverse=reverse)


                    elif item.is_a('IFCPOLYGONALFACESET'):
                        # IFCPOLYGONALFACESET: Verwende unseren bestehenden Code
                        coordinates_list, indices_list, voids_indices_list = extract_geometry_info_from_shape_aspect(shape_aspect)
                        cleaned_indices_list = clean_indices_list(indices_list, voids_indices_list)

                        # Erstellen der Vertex-Liste (Punkte) aus den extrahierten Koordinaten
                        vertices = []
                        for coord in coordinates_list:
                            vertex = Vertex.ByCoordinates(x=coord[0], y=coord[1], z=coord[2])
                            vertices.append(vertex)

                        # Erstellen der Faces (Flächen) aus den bereinigten Indizes
                        faces = []
                        for face_indices in cleaned_indices_list:
                            face_vertices = [vertices[i-1] for i in face_indices]  # Die Indizes sind 1-basiert, Python verwendet jedoch 0-basierte Indizes
                            face = Face.ByVertices(face_vertices)
                            faces.append(face)

                        # Erstellen der Cell (Volumen) aus den Faces
                        cell = Cell.ByFaces(faces)

                    else:
                        print("Unknown Representation")
            else:
                print("Shape aspect does not have correct IFCSHAPEREPRESENTATION")

        # Output to confirm that the cell has been created
        print("Cell created:", cell)

        Topology.AddDictionary(cell,Dictionary.ByKeyValue("material",material))


        ### Transformation from local CoordSystem to ProjectCoordSystem

        rotation_matrix = create_rotation_matrix(wall_axis, wall_ref_direction)
        axis, angle = rotation_matrix_to_axis_angle(rotation_matrix)

        # Test if Vector is Null
        if np.allclose(axis, [0, 0, 0]) and np.isclose(angle, 0):
            # No Rotation needed
            print("Keine Rotation erforderlich.")
            rotated_topology = cell  # No changes
        elif np.allclose(axis, [0, 0, 0]) and np.isclose(angle, 180):
            # Special Case "Mirroring"
            print("Sonderfall 180-Grad-Rotation erkannt.")
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
            x=wall_rel_placement[0], 
            y=wall_rel_placement[1], 
            z=wall_rel_placement[2]
        )

        # Output the transformed topology to verify the translation
        print("Transformed Topology:", final_topology)

        cells.append(final_topology)

    if cells != []:
        # Create dictionary with walls
        dic_walls[wall_guid] = cells

        # Create cell complex, add to cluster
        complex = CellComplex.ByCells(cells)
        guiddic = Dictionary.ByKeyValue("guid",wall_guid)
        Topology.AddDictionary(complex,guiddic)
        topo_walls.append(complex)

topo_cluster = Cluster.ByTopologies(topo_walls) 

topologies_in_storey = [element for element in topo_walls if element is not None]

touching_walls = []

for i in range(len(topologies_in_storey)):
    print(f"Check of Wall {i} / {len(topologies_in_storey)}")
    for j in range(i + 1, len(topologies_in_storey)):
        if find_touching_walls(topologies_in_storey[i], topologies_in_storey[j]):
            touching_walls.append((i, j))

index_to_guid = {i: get_ifc_guid(topo) for i, topo in enumerate(topologies_in_storey)}

touching_walls_dict = {index_to_guid[i]: [] for i in range(len(topologies_in_storey))}

for i, j in touching_walls:
    touching_walls_dict[index_to_guid[i]].append(index_to_guid[j])
    touching_walls_dict[index_to_guid[j]].append(index_to_guid[i])

output_file = 'Output06_Wall_Adjacancy.csv'

with open(output_file, mode='w', newline='') as file:
    writer = csv.writer(file, delimiter=';')
    for key, value in touching_walls_dict.items():
        touching_guids = ",".join(value)
        row = [key, touching_guids]
        writer.writerow(row)

print(f'Results written to {output_file}')