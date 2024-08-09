from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
import csv
import ifcopenshell

def find_touching_walls(topology1, topology2):
    cells1 = Topology.Cells(topology1)
    cells2 = Topology.Cells(topology2)

    for index1, cell1 in enumerate(cells1):
        for index2, cell2 in enumerate(cells2):
            # Merging the two cells
            merged_cell = Topology.Merge(cell1, cell2)

            # Getting the shared faces
            shared_faces = Topology.SharedFaces((Topology.Cells(merged_cell)[0]), (Topology.Cells(merged_cell)[1]))
            
            if shared_faces:
                return True  # Berührung festgestellt, Suche abbrechen
            
    return False  # Keine Berührung festgestellt


def main(ifc_file, storey_name):

    # Create topology from the IFC file
    topology = Topology.ByIFCFile(file=ifc_file, transferDictionaries=True, includeTypes=['IfcWall'])
    print("Initial topology created successfully.")

    # Find all IfcWalls in the storey and collect their GUIDs
    wall_guids_in_storey = []

    # Find the IfcBuildingStorey for each IfcWall
    for wall in ifc_file.by_type('IfcWall'):
        for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if wall in rel.RelatedElements:
                storey = rel.RelatingStructure
                if storey and storey.Name == storey_name:
                    wall_guids_in_storey.append(wall.GlobalId)
                break  # Sobald die Etage gefunden wurde, können wir die Schleife verlassen

    topologies_in_storey = []

    for topo in topology:
        topo_dict = Topology.Dictionary(topo)
        topo_guid = Dictionary.ValueAtKey(topo_dict, "IFC_guid")
        if topo_guid in wall_guids_in_storey:
            topologies_in_storey.append(topo)

    touching_walls = []

    for i in range(len(topologies_in_storey)):
        print(f"Check of Wall {i}")
        for j in range(i + 1, len(topologies_in_storey)):
            if find_touching_walls(topologies_in_storey[i], topologies_in_storey[j]):
                touching_walls.append((i, j))

    # Function to get the IFC GUID of a topology
    def get_ifc_guid(topo):
        topo_dict = Topology.Dictionary(topo)
        return Dictionary.ValueAtKey(topo_dict, "IFC_guid")

    # Create a dictionary to map index to IFC GUID
    index_to_guid = {i: get_ifc_guid(topo) for i, topo in enumerate(topologies_in_storey)}

    # Create a dictionary to store the touching walls information
    touching_walls_dict = {index_to_guid[i]: [] for i in range(len(topologies_in_storey))}

    # Populate the dictionary with touching walls information
    for i, j in touching_walls:
        touching_walls_dict[index_to_guid[i]].append(index_to_guid[j])
        touching_walls_dict[index_to_guid[j]].append(index_to_guid[i])

    # Write the results to a CSV file
    output_file = 'Output06_Wall_Adjacancy.csv'

    with open(output_file, mode='w', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        for key, value in touching_walls_dict.items():
            row = [key] + value
            writer.writerow(row)

    print(f'Results written to {output_file}')


if __name__ == "__main__":
    main()
