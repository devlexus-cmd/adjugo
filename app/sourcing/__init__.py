"""
Moteur de sourcing anti-hallucination.

Principe : aucune donnée affichée si elle n'a pas été récupérée d'une source
officielle identifiée. Chaque enregistrement porte sa provenance (source, URL,
référence officielle, date de récupération) et un niveau de confiance.
Le LLM ne sert qu'à structurer/résumer/expliquer des données déjà récupérées.
"""
