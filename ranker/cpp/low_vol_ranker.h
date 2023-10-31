#ifndef LOW_VOL_RANKER_H
#define LOW_VOL_RANKER_H

#include <queue>
#include <string>
#include <vector>
#include <utility>

#include "player.h"

struct Comp {
    int id1;
    int id2;
    float score;
};

/// @brief Accepts pairwise comparisons and outputs rankings
/// @details For low volume comparisons
class LowVolRanker {
  public:

  LowVolRanker(bool avoid_twice=true);

  void addPlayer(float rating=0, float rd=350);

  /// @brief Get the most useful comparison to do next 
  std::pair<int, int> get_next_comp() const;
  /// @brief Update ratings based on new comparison
  void receive_comp(int id1, int id2, float score, bool update=true);
  /// @brief Use computationally heavy method to estimate ratings
  void adjust_ratings();
  /// @brief Write ratings into a file
  void dump_ratings(std::string filename) const;

  private:
  /// @brief Objects to rank
  std::vector<Player> players_;
  /// @brief Comparisons done so far
  std::vector<Comp> comps_;
  /// @brief Players to avoid in the next comparison
  std::vector<Player> avoid_;
  /// @brief Whether to avoid repeating players in the next comparison
  bool avoid_twice_;

  /// @brief Get the player with the highest RD
  int get_best_player() const;
  /// @brief Get the opponent with the highest score variance 
  int get_best_opp(int id) const;


};

#endif