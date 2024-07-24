#r: topologicpy

import topologicpy as tp

from topologicpy.Vertex import Vertex
from topologicpy.Edge import Edge
from topologicpy.Wire import Wire
from topologicpy.Face import Face
from topologicpy.Shell import Shell
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Cluster import Cluster
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Graph import Graph
from topologicpy.Plotly import Plotly
from topologicpy.Color import Color
from topologicpy.Vector import Vector
from topologicpy.Helper import Helper
from topologicpy.Graph import Graph
import math

v1 = Vertex.ByCoordinates(10,0,0)
print(v1)
print(Vertex.Coordinates(v1))
print(Vertex.X(v1))

v2 = Vertex.ByCoordinates(10,10,0)

e1 = Edge.ByVertices([v1,v2])
print(e1)

Topology.Show(e1, vertexSize=5)

c = Cell.Prism(width=5, length=3, height=2, uSides=3, vSides=10, wSides=4)
Topology.Show(c, xAxis=True, yAxis=True, zAxis=True)

cc = CellComplex.Prism()
Topology.Show(cc)

exploded = Topology.Explode(cc, scale=1.75, typeFilter="face")
Topology.Show(exploded)

cells = CellComplex.Cells(cc)
c1 = cells[0]
neighbours = Topology.AdjacentTopologies(c1, cc)
neighbours = Cluster.ByTopologies(neighbours)
print(neighbours)

data01 = Plotly.DataByTopology(c1, faceColor="yellow", faceOpacity=1)
data02 = Plotly.DataByTopology(neighbours, faceColor="red")
fig = Plotly.FigureByData(data01+data02)
Plotly.Show(fig)

cells = Cluster.Cells(neighbours)
cells.append(c1)
new_cc = CellComplex.ByCells(cells)
Topology.Show(new_cc)

g = Graph.ByTopology(new_cc, toExteriorTopologies=True)
Graph.Show(g)

data01 = Plotly.DataByGraph(g)
data02 = Plotly.DataByTopology(new_cc, faceColor="red")
fig = Plotly.FigureByData(data01+data02)
Plotly.Show(fig)

print(Cell.Volume(c1))