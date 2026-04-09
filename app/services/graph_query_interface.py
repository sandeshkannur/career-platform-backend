# app/services/graph_query_interface.py
"""
Abstract interface for graph queries.
PostgreSQL implementation today. Neo4j implementation later.
Swap the implementation in graph_query_service.py — nothing else changes.
"""
from abc import ABC, abstractmethod


class GraphQueryInterface(ABC):

    @abstractmethod
    def get_aq_influence_map(self, student_id: int) -> dict:
        """
        Returns which AQs most influence which careers for this student.
        Output shape:
        {
          "aq_influences": [
            {
              "aq_code": "AQ_01",
              "aq_name": "Curiosity Drive",
              "student_score": 74.3,
              "top_careers": [
                {"title": "Journalist", "cluster": "Arts & A/V", "influence_weight": 0.42},
                {"title": "Research Scientist", "cluster": "STEM", "influence_weight": 0.38}
              ],
              "top_clusters": [
                {"cluster": "Education", "influence_weight": 0.45},
                {"cluster": "STEM", "influence_weight": 0.38}
              ]
            }
          ]
        }
        """
        pass

    @abstractmethod
    def get_whatif_simulation(
        self, student_id: int, aq_code: str, delta: float
    ) -> dict:
        """
        Simulates career ranking change if student improves a specific AQ by delta points.
        Output shape:
        {
          "aq_code": "AQ_01",
          "aq_name": "Curiosity Drive",
          "delta": 10.0,
          "before": [
            {"rank": 1, "title": "Special Education Teacher", "cluster": "Education", "score": 73.6}
          ],
          "after": [
            {"rank": 1, "title": "Journalist", "cluster": "Arts & A/V", "score": 76.2}
          ],
          "entered_top9": [{"title": "Research Scientist", "cluster": "STEM", "score": 74.1}],
          "left_top9": [{"title": "Actor", "cluster": "Arts & A/V", "score": 71.2}],
          "rank_changes": [
            {"title": "Journalist", "before_rank": 5, "after_rank": 1, "change": 4}
          ]
        }
        """
        pass

    @abstractmethod
    def get_cluster_reachability(self, student_id: int) -> dict:
        """
        Returns 3-zone cluster map for this student.
        Output shape:
        {
          "reachable_now": [
            {"cluster": "Education", "score": 72.1, "top_career": "Teacher", "career_count": 3}
          ],
          "reachable_with_effort": [
            {"cluster": "Health Sci", "score": 47.3, "gap": 2.7, "top_career": "Nurse"}
          ],
          "aspirational": [
            {"cluster": "Info Tech", "score": 31.2, "gap": 18.8, "top_career": "Software Engineer"}
          ]
        }
        """
        pass

    @abstractmethod
    def get_career_pathway(self, student_id: int, target_career_title: str) -> dict:
        """
        Returns what the student needs to improve to reach a target career.
        Output shape:
        {
          "target_career": "Data Scientist",
          "target_cluster": "Info Tech",
          "current_score": 41.2,
          "target_score": 65.0,
          "gap": 23.8,
          "reachable": false,
          "skill_gaps": [
            {
              "skill": "Critical Thinking & Problem Solving",
              "current_score": 65.0,
              "required_score": 80.0,
              "gap": 15.0,
              "career_weight": 35.0,
              "driving_aqs": [
                {"aq_code": "AQ_02", "aq_name": "Inquiry Framing", "contribution": 0.25}
              ]
            }
          ],
          "recommended_focus_aqs": [
            {"aq_code": "AQ_02", "aq_name": "Inquiry Framing", "impact_score": 0.87}
          ]
        }
        """
        pass
