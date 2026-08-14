"""Worker determinístico de processamento e exportação CAD.

Os módulos pesados são importados somente pelo comando que precisa deles. Isso
mantém ingestão de PDF independente do renderer CAD e de Matplotlib.
"""
