# app/services/graph_query_service.py
"""
Factory that returns the correct GraphQueryInterface implementation.
TODAY: PostgreSQL
FUTURE: swap PostgresGraphQuery for Neo4jGraphQuery here — nothing else changes.
"""
from sqlalchemy.orm import Session
from app.services.graph_query_interface import GraphQueryInterface
from app.services.graph_query_postgres import PostgresGraphQuery


def get_graph_query_service(db: Session) -> GraphQueryInterface:
    """
    Returns the active graph query implementation.
    To switch to Neo4j:
      1. Create app/services/graph_query_neo4j.py implementing GraphQueryInterface
      2. Import Neo4jGraphQuery here
      3. Return Neo4jGraphQuery(neo4j_driver) instead
    """
    return PostgresGraphQuery(db)
