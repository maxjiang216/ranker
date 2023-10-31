#include "low_vol_ranker.h"

#include <algorithm>

LowVolRanker::LowVolRanker(bool avoid_twice):
    avoid_twice_{avoid_twice} {}

void LowVolRanker::addPlayer(float rating, float rd) {
    players_.emplace_back(rating, rd);
}

std::pair<int, int> LowVolRanker::get_next_comp() const {
    int id1 = get_best_player();
    int id2 = get_best_opp(id1);
    return std::make_pair(id1, id2);
}

void LowVolRanker::receive_comp(int id1, int id2, float score, bool update) {
    comps_.emplace_back(id1, id2, score);
    if (update) {
        players_[id1].update(score, players_[id2].get_rating(), players_[id2].get_rd());
        players_[id2].update(1 - score, players_[id1].get_rating(), players_[id1].get_rd());
        if (avoid_twice_) {
            avoid_.clear();
            avoid_.push_back(id1);
            avoid_.push_back(id2);
        }
    }
}

void LowVolRanker::adjust_ratings() {
    // TODO
    // Use MLE
}

int LowVolRanker::get_best_player() const {
    int max_id = -1;
    float max_rd = 0;
    for (size_t i = 0; i < players_.size(); i++) {
        if (players_[i].get_rd() > max_rd && std::find(avoid_.begin(), avoid_.end(), i) == avoid_.end()) {
            max_rd = players_[i].get_rd();
            max_id = i;
        }
    }
    return max_id;
}

int LowVolRanker::get_best_opp(int id) const {
    int max_id = -1;
    float max_var = 0;
    for (size_t i = 0; i < players_.size(); i++) {
        if (i != id && std::find(avoid_.begin(), avoid_.end(), i) == avoid_.end()) {
            float var = players_[id].compute_score_var(players_[i].get_rating(), players_[i].get_rd());
            if (var > max_var) {
                max_var = var;
                max_id = i;
            }
        }
    }
    return max_id;
}

void LowVolRanker::dump_ratings(std::string filename) const {
    // TODO
}