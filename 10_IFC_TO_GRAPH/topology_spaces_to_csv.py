import csv
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary

def get_cell_OID(cell):
    dictionary = Topology.Dictionary(cell)
    if dictionary:
        name = Dictionary.ValueAtKey(dictionary, "Name")
        return name if name else str(cell)
    return str(cell)


def main(building):

    # Extract all Cells from the Building
    cells = Topology.Cells(building)


    # Dictionary to store touching Cells with their names
    touching_cells = {}

    # Function to check if two cells share a face
    def cells_share_face(cell1, cell2):
        shared_faces = Topology.SharedFaces(cell1, cell2)
        return len(shared_faces) > 0

    # Iterate through each pair of Cells to find touching Cells
    for i, cell1 in enumerate(cells):
        touching = []
        for j, cell2 in enumerate(cells):
            if i != j and cells_share_face(cell1, cell2):
                touching.append(get_cell_OID(cell2))
        if touching:
            touching_cells[get_cell_OID(cell1)] = touching

    # Prepare data for CSV
    csv_data = []
    for cell_name, touch_cell_names in touching_cells.items():
        if cell_name not in touch_cell_names:
            row = [cell_name] + touch_cell_names
            csv_data.append(row)

    # Write to CSV
    with open('Output01_RoomToRoom_BySeparationLine.csv', mode='w', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        for row in csv_data:
            writer.writerow(row)

    print("Data has been written to Output01_RoomToRoom_BySeparationLine.csv")


if __name__ == "__main__":
    main()