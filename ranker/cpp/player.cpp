#include "player.h"

#include <cmath>

Player::Player(int id, float rating, float rd):
    id_{id}, rating_{rating}, rd_{rd}, num_comps_(0) {}

void Player::set_rating(float rating) {
    rating = rating;
}

void Player::set_rd(float rd) {
    rd = rd;
}

void Player::update(float score, float opp_rating, float opp_rd) {
    float d2 = get_d2(opp_rating, opp_rd);
    float new_rating = get_new_rating(score, opp_rating, opp_rd, d2);
    float new_rd = get_new_rd(d2);
    set_rating(new_rating);
    set_rd(new_rd);
    num_comps_++;
}

float Player::get_new_rating(float score, float opp_rating, float opp_rd, float d2) const {
    float g = get_g(opp_rd);
    return rating_ + Q / (1 / (rd_ * rd_) + 1 / d2) * g * (score - get_expected_score(opp_rating, opp_rd, g));
}

float Player::get_new_rd(float d2) const {
    return sqrt(1 / (1 / (rd_ * rd_) + 1 / d2));
}   

float Player::get_d2(float opp_rating, float opp_rd) const {
    return 1 / (Q * Q * get_g(opp_rd) * get_g(opp_rd) * get_expected_score(opp_rating, opp_rd, get_g(opp_rd)) * (1 - get_expected_score(opp_rating, opp_rd, get_g(opp_rd))));
}

float Player::get_g(float opp_rd) const {
    return 1 / sqrt(1 + 3 * Q * Q * opp_rd * opp_rd / M_PI / M_PI);
}

float Player::get_expected_score(float opp_rating, float opp_rd, float g) const {
    return 1 / (1 + pow(10, -g * (rating_ - opp_rating) / 400));
}

float Player::compute_score_var(float opp_rating, float opp_rd) const {
    float p10 = pow(10, (rating_ - opp_rating) / 400);
    float frac = (p10 / ((1 + p10) * (1 + p10)));
    float frac2 = frac * frac;
    return frac2 * (rd_ * rd_ + opp_rd * opp_rd);
}
