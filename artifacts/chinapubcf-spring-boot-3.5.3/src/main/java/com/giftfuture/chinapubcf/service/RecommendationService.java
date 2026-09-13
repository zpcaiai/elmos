package com.giftfuture.chinapubcf.service;

import com.giftfuture.chinapubcf.model.Book;
import com.giftfuture.chinapubcf.model.Rating;
import com.giftfuture.chinapubcf.model.Recommendation;
import com.giftfuture.chinapubcf.repository.BookRepository;
import com.giftfuture.chinapubcf.repository.RatingRepository;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class RecommendationService {
    private final RatingRepository ratings;
    private final BookRepository books;

    public RecommendationService(RatingRepository ratings, BookRepository books) {
        this.ratings = ratings;
        this.books = books;
    }

    public List<Recommendation> userBased(long userId, int limit) {
        RatingsMatrix matrix = RatingsMatrix.of(ratings.findAll());
        Map<Long, Double> target = matrix.byUser.getOrDefault(userId, Map.of());
        Map<Long, double[]> weighted = new HashMap<>();
        matrix.byUser.forEach((otherUser, otherRatings) -> {
            if (otherUser == userId) return;
            double similarity = pearson(target, otherRatings);
            if (similarity <= 0) return;
            otherRatings.forEach((bookId, score) -> {
                if (!target.containsKey(bookId)) {
                    double[] totals = weighted.computeIfAbsent(bookId, ignored -> new double[2]);
                    totals[0] += similarity * score;
                    totals[1] += Math.abs(similarity);
                }
            });
        });
        return materialize(scores(weighted), target.keySet(), limit, matrix);
    }

    public List<Recommendation> itemBased(long userId, int limit) {
        RatingsMatrix matrix = RatingsMatrix.of(ratings.findAll());
        Map<Long, Double> target = matrix.byUser.getOrDefault(userId, Map.of());
        Map<Long, double[]> weighted = new HashMap<>();
        for (Long candidate : matrix.byBook.keySet()) {
            if (target.containsKey(candidate)) continue;
            for (Map.Entry<Long, Double> purchased : target.entrySet()) {
                double similarity = pearson(matrix.byBook.get(candidate), matrix.byBook.get(purchased.getKey()));
                if (similarity > 0) {
                    double[] totals = weighted.computeIfAbsent(candidate, ignored -> new double[2]);
                    totals[0] += similarity * purchased.getValue();
                    totals[1] += Math.abs(similarity);
                }
            }
        }
        return materialize(scores(weighted), target.keySet(), limit, matrix);
    }

    public List<Recommendation> slopeOne(long userId, int limit) {
        RatingsMatrix matrix = RatingsMatrix.of(ratings.findAll());
        Map<Long, Double> target = matrix.byUser.getOrDefault(userId, Map.of());
        Map<Long, Map<Long, double[]>> deviations = new HashMap<>();
        matrix.byUser.values().forEach(userRatings -> userRatings.forEach((leftId, leftScore) ->
                userRatings.forEach((rightId, rightScore) -> {
                    if (leftId.equals(rightId)) return;
                    double[] aggregate = deviations
                            .computeIfAbsent(leftId, ignored -> new HashMap<>())
                            .computeIfAbsent(rightId, ignored -> new double[2]);
                    aggregate[0] += leftScore - rightScore;
                    aggregate[1] += 1;
                })));
        Map<Long, double[]> weighted = new HashMap<>();
        deviations.forEach((candidate, against) -> {
            if (target.containsKey(candidate)) return;
            against.forEach((ratedBook, aggregate) -> {
                Double userScore = target.get(ratedBook);
                if (userScore != null && aggregate[1] > 0) {
                    double[] totals = weighted.computeIfAbsent(candidate, ignored -> new double[2]);
                    totals[0] += (aggregate[0] / aggregate[1] + userScore) * aggregate[1];
                    totals[1] += aggregate[1];
                }
            });
        });
        return materialize(scores(weighted), target.keySet(), limit, matrix);
    }

    public List<Recommendation> combined(long userId, int limit) {
        Map<Long, double[]> combined = new LinkedHashMap<>();
        List.of(userBased(userId, limit * 2), itemBased(userId, limit * 2), slopeOne(userId, limit * 2))
                .forEach(recommendations -> recommendations.forEach(recommendation -> {
                    double[] aggregate = combined.computeIfAbsent(recommendation.book().bookId(), ignored -> new double[2]);
                    aggregate[0] += recommendation.score();
                    aggregate[1] += 1;
                }));
        Map<Long, Book> byId = books.findByIds(new ArrayList<>(combined.keySet())).stream()
                .collect(Collectors.toMap(Book::bookId, Function.identity()));
        return combined.entrySet().stream()
                .filter(entry -> byId.containsKey(entry.getKey()))
                .map(entry -> new Recommendation(byId.get(entry.getKey()), entry.getValue()[0] / entry.getValue()[1]))
                .sorted(Comparator.comparingDouble(Recommendation::score).reversed()
                        .thenComparingLong(value -> value.book().bookId()))
                .limit(boundedLimit(limit))
                .toList();
    }

    private List<Recommendation> materialize(Map<Long, Double> candidateScores, Set<Long> excluded,
                                             int limit, RatingsMatrix matrix) {
        Map<Long, Double> scores = new HashMap<>(candidateScores);
        matrix.byBook.forEach((bookId, bookRatings) -> {
            if (!excluded.contains(bookId)) {
                scores.putIfAbsent(bookId, bookRatings.values().stream().mapToDouble(Double::doubleValue).average().orElse(0));
            }
        });
        if (scores.isEmpty()) {
            books.findPage(1, 100).stream()
                    .filter(book -> !excluded.contains(book.bookId()))
                    .forEach(book -> scores.put(book.bookId(), 0.0));
        }
        Map<Long, Book> byId = books.findByIds(new ArrayList<>(scores.keySet())).stream()
                .collect(Collectors.toMap(Book::bookId, Function.identity()));
        return scores.entrySet().stream()
                .filter(entry -> byId.containsKey(entry.getKey()))
                .map(entry -> new Recommendation(byId.get(entry.getKey()), clamp(entry.getValue())))
                .sorted(Comparator.comparingDouble(Recommendation::score).reversed()
                        .thenComparingLong(value -> value.book().bookId()))
                .limit(boundedLimit(limit))
                .toList();
    }

    private static Map<Long, Double> scores(Map<Long, double[]> weighted) {
        return weighted.entrySet().stream()
                .filter(entry -> entry.getValue()[1] > 0)
                .collect(Collectors.toMap(Map.Entry::getKey,
                        entry -> entry.getValue()[0] / entry.getValue()[1]));
    }

    private static double pearson(Map<Long, Double> left, Map<Long, Double> right) {
        if (left == null || right == null) return 0;
        List<Long> common = left.keySet().stream().filter(right::containsKey).toList();
        if (common.size() < 2) return 0;
        double leftMean = common.stream().mapToDouble(left::get).average().orElse(0);
        double rightMean = common.stream().mapToDouble(right::get).average().orElse(0);
        double numerator = 0;
        double leftSquares = 0;
        double rightSquares = 0;
        for (Long key : common) {
            double leftDelta = left.get(key) - leftMean;
            double rightDelta = right.get(key) - rightMean;
            numerator += leftDelta * rightDelta;
            leftSquares += leftDelta * leftDelta;
            rightSquares += rightDelta * rightDelta;
        }
        double denominator = Math.sqrt(leftSquares * rightSquares);
        return denominator == 0 ? 0 : numerator / denominator;
    }

    private static int boundedLimit(int limit) {
        return Math.max(1, Math.min(limit, 100));
    }

    private static double clamp(double value) {
        return Math.max(0, Math.min(5, value));
    }

    private record RatingsMatrix(Map<Long, Map<Long, Double>> byUser,
                                 Map<Long, Map<Long, Double>> byBook) {
        static RatingsMatrix of(List<Rating> ratings) {
            Map<Long, Map<Long, Double>> byUser = new HashMap<>();
            Map<Long, Map<Long, Double>> byBook = new HashMap<>();
            ratings.forEach(rating -> {
                byUser.computeIfAbsent(rating.userId(), ignored -> new HashMap<>())
                        .put(rating.bookId(), rating.score());
                byBook.computeIfAbsent(rating.bookId(), ignored -> new HashMap<>())
                        .put(rating.userId(), rating.score());
            });
            return new RatingsMatrix(byUser, byBook);
        }
    }
}
