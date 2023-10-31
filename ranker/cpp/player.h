#ifndef PLAYER_H
#define PLAYER_H

#include <cmath>

/// @brief Stores a player's rating and RD
/// @details Updates using the Glicko system
class Player {
  public:

  Player(int id, float rating=0, float rd=350);

  float get_rating() const { return rating_; }
  float get_rd() const { return rd_; }
  int get_num_comps() const { return num_comps_; }
  void set_rating(float rating);
  void set_rd(float rd);

  float compute_score_var(float opp_rating, float opp_rd) const;

  void update(float score, float opp_rating, float opp_rd);
    
  private:
    const float Q = log(10) / 400;
    int id_;
    float rating_;
    float rd_;
    int num_comps_;

    float get_expected_score(float opp_rating, float opp_rd, float g) const;
    float get_d2(float opp_rating, float opp_rd) const;
    float get_g(float opp_rd) const;
    float get_new_rating(float score, float opp_rating, float opp_rd, float d2) const;
    float get_new_rd(float d2) const;

};

#endif