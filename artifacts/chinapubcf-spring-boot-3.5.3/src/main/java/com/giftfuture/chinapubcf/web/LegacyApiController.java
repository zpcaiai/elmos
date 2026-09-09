package com.giftfuture.chinapubcf.web;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.giftfuture.chinapubcf.model.Book;
import com.giftfuture.chinapubcf.model.Rating;
import com.giftfuture.chinapubcf.model.Recommendation;
import com.giftfuture.chinapubcf.model.UserAccount;
import com.giftfuture.chinapubcf.repository.BookRepository;
import com.giftfuture.chinapubcf.repository.RatingRepository;
import com.giftfuture.chinapubcf.service.AccountService;
import com.giftfuture.chinapubcf.service.RatingService;
import com.giftfuture.chinapubcf.service.RecommendationService;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;

@RestController
public class LegacyApiController {
    private static final String SESSION_USER_ID = "userId";
    private static final int PAGE_SIZE = 10;

    private final BookRepository books;
    private final RatingRepository ratings;
    private final AccountService accounts;
    private final RatingService ratingService;
    private final RecommendationService recommendations;
    private final ObjectMapper json;

    public LegacyApiController(BookRepository books, RatingRepository ratings, AccountService accounts,
                               RatingService ratingService, RecommendationService recommendations,
                               ObjectMapper json) {
        this.books = books;
        this.ratings = ratings;
        this.accounts = accounts;
        this.ratingService = ratingService;
        this.recommendations = recommendations;
        this.json = json;
    }

    @GetMapping(path = "/books", produces = MediaType.APPLICATION_JSON_VALUE)
    public List<Book> books(@RequestParam(defaultValue = "1") int pageno, HttpSession session) {
        if (pageno < 1) throw new IllegalArgumentException("pageno must be positive");
        long count = books.count();
        session.setAttribute("pageno", pageno);
        session.setAttribute("bookCount", count);
        session.setAttribute("allpages", (count + PAGE_SIZE - 1) / PAGE_SIZE);
        return books.findPage(pageno, PAGE_SIZE);
    }

    @PostMapping(path = "/books", produces = MediaType.APPLICATION_JSON_VALUE)
    public List<Book> booksPost(@RequestParam(defaultValue = "1") int pageno, HttpSession session) {
        return books(pageno, session);
    }

    @GetMapping(path = "/booklist", produces = MediaType.APPLICATION_JSON_VALUE)
    public List<Recommendation> purchasedBooks(@RequestParam long userId, HttpSession session) {
        requireSameUser(session, userId);
        Map<Long, Double> byBook = ratings.findByUser(userId).stream()
                .collect(java.util.stream.Collectors.toMap(Rating::bookId, Rating::score));
        return books.findByUser(userId).stream()
                .map(book -> new Recommendation(book, byBook.getOrDefault(book.bookId(), 0.0)))
                .toList();
    }

    @PostMapping(path = "/booklist", produces = MediaType.APPLICATION_JSON_VALUE)
    public List<Recommendation> purchasedBooksPost(@RequestParam long userId, HttpSession session) {
        return purchasedBooks(userId, session);
    }

    @GetMapping(path = "/user", produces = MediaType.APPLICATION_JSON_VALUE)
    public UserAccount.PublicView login(@RequestParam String email, @RequestParam String usrpwd,
                                        HttpSession session) {
        UserAccount account = accounts.authenticate(email, usrpwd)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid credentials"));
        bindSession(session, account);
        return account.publicView();
    }

    @PostMapping(path = "/user", produces = MediaType.APPLICATION_JSON_VALUE)
    public UserAccount.PublicView loginPost(@RequestParam String email, @RequestParam String usrpwd,
                                            HttpSession session) {
        return login(email, usrpwd, session);
    }

    @GetMapping(path = {"/sessionlogin", "/SessionLoginServlet"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public UserAccount.PublicView currentSession(HttpSession session) {
        return currentAccount(session).publicView();
    }

    @PostMapping(path = {"/sessionlogin", "/SessionLoginServlet"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public UserAccount.PublicView currentSessionPost(HttpSession session) {
        return currentSession(session);
    }

    @PostMapping(path = {"/register", "/RegisterServlet"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<UserAccount.PublicView> register(
            @RequestParam String name,
            @RequestParam String email,
            @RequestParam String usrpwd,
            @RequestParam(defaultValue = "") String status,
            @RequestParam(defaultValue = "") String admirefield,
            @RequestParam(defaultValue = "") String expertat,
            @RequestParam(defaultValue = "") String tag,
            @RequestParam(defaultValue = "") String knowfrom) {
        UserAccount created = accounts.register(new AccountService.Registration(
                name, email, usrpwd, status, admirefield, expertat, tag, knowfrom));
        return ResponseEntity.status(HttpStatus.CREATED).body(created.publicView());
    }

    @GetMapping(path = {"/register", "/RegisterServlet"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<UserAccount.PublicView> registerLegacyGet(
            @RequestParam String name,
            @RequestParam String email,
            @RequestParam String usrpwd,
            @RequestParam(defaultValue = "") String status,
            @RequestParam(defaultValue = "") String admirefield,
            @RequestParam(defaultValue = "") String expertat,
            @RequestParam(defaultValue = "") String tag,
            @RequestParam(defaultValue = "") String knowfrom) {
        return register(name, email, usrpwd, status, admirefield, expertat, tag, knowfrom);
    }

    @PostMapping(path = {"/rating", "/RatingServlet"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> rate(@RequestParam long userId, @RequestParam String bookIdScores,
                                    HttpSession session) {
        long authenticated = authenticatedUserId(session);
        int recorded = ratingService.record(authenticated, userId, bookIdScores);
        return Map.of("recorded", recorded, "userId", userId);
    }

    @GetMapping(path = {"/rating", "/RatingServlet"}, produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> rateLegacyGet(@RequestParam long userId, @RequestParam String bookIdScores,
                                             HttpSession session) {
        return rate(userId, bookIdScores, session);
    }

    @PostMapping(path = {"/logout", "/LogoutServlet"})
    public ResponseEntity<Void> logout(HttpSession session) {
        session.invalidate();
        return ResponseEntity.noContent().build();
    }

    @GetMapping(path = {"/logout", "/LogoutServlet"})
    public ResponseEntity<Void> logoutGet(HttpSession session) {
        return logout(session);
    }

    @GetMapping(path = "/userrecmd")
    public ResponseEntity<String> userRecommendations(@RequestParam long userId,
                                                      @RequestParam(defaultValue = "20") int count,
                                                      @RequestParam(defaultValue = "text") String format,
                                                      HttpSession session) {
        return recommend(userId, count, format, session, recommendations::userBased);
    }

    @GetMapping(path = "/itemrecmd")
    public ResponseEntity<String> itemRecommendations(@RequestParam long userId,
                                                      @RequestParam(defaultValue = "20") int count,
                                                      @RequestParam(defaultValue = "text") String format,
                                                      HttpSession session) {
        return recommend(userId, count, format, session, recommendations::itemBased);
    }

    @GetMapping(path = "/sloperecmd")
    public ResponseEntity<String> slopeRecommendations(@RequestParam long userId,
                                                       @RequestParam(defaultValue = "20") int count,
                                                       @RequestParam(defaultValue = "text") String format,
                                                       HttpSession session) {
        return recommend(userId, count, format, session, recommendations::slopeOne);
    }

    @GetMapping(path = {"/chinapub", "/ChinapubRecommanderServlet"})
    public ResponseEntity<String> combinedRecommendations(@RequestParam long userId,
                                                          @RequestParam(defaultValue = "20") int count,
                                                          @RequestParam(defaultValue = "text") String format,
                                                          HttpSession session) {
        return recommend(userId, count, format, session, recommendations::combined);
    }

    @PostMapping(path = {"/userrecmd", "/itemrecmd", "/sloperecmd", "/chinapub", "/ChinapubRecommanderServlet"})
    public ResponseEntity<String> recommendationsPost(jakarta.servlet.http.HttpServletRequest request,
                                                      @RequestParam long userId,
                                                      @RequestParam(defaultValue = "20") int count,
                                                      @RequestParam(defaultValue = "text") String format,
                                                      HttpSession session) {
        return switch (request.getServletPath()) {
            case "/userrecmd" -> userRecommendations(userId, count, format, session);
            case "/itemrecmd" -> itemRecommendations(userId, count, format, session);
            case "/sloperecmd" -> slopeRecommendations(userId, count, format, session);
            default -> combinedRecommendations(userId, count, format, session);
        };
    }

    private ResponseEntity<String> recommend(long userId, int count, String format, HttpSession session,
                                             BiFunction<Long, Integer, List<Recommendation>> algorithm) {
        requireSameUser(session, userId);
        List<Recommendation> result = algorithm.apply(userId, count);
        MediaType contentType;
        String body;
        switch (format.toLowerCase(java.util.Locale.ROOT)) {
            case "json" -> {
                contentType = MediaType.APPLICATION_JSON;
                body = writeJson(result);
            }
            case "xml" -> {
                contentType = MediaType.APPLICATION_XML;
                body = toXml(result);
            }
            case "text" -> {
                contentType = MediaType.TEXT_PLAIN;
                body = result.stream()
                        .map(value -> "Book:\tName: " + value.book().name() + "\tScore:\t" + value.score())
                        .collect(java.util.stream.Collectors.joining("\n"));
            }
            default -> throw new IllegalArgumentException("format must be text, json, or xml");
        }
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).contentType(contentType).body(body);
    }

    private String writeJson(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException impossible) {
            throw new IllegalStateException("could not serialize recommendation", impossible);
        }
    }

    private static String toXml(List<Recommendation> values) {
        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?><recommendedItems>");
        values.forEach(value -> xml.append("<item><value>").append(value.score())
                .append("</value><id>").append(value.book().bookId()).append("</id></item>"));
        return xml.append("</recommendedItems>").toString();
    }

    private UserAccount currentAccount(HttpSession session) {
        return accounts.findById(authenticatedUserId(session))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "session user no longer exists"));
    }

    private static long authenticatedUserId(HttpSession session) {
        Object value = session.getAttribute(SESSION_USER_ID);
        if (!(value instanceof Number number)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "authentication required");
        }
        return number.longValue();
    }

    private static void requireSameUser(HttpSession session, long requestedUserId) {
        if (authenticatedUserId(session) != requestedUserId) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "cross-user access denied");
        }
    }

    private static void bindSession(HttpSession session, UserAccount account) {
        session.setAttribute(SESSION_USER_ID, account.userId());
        session.setAttribute("username", account.name());
        session.setAttribute("uemail", account.email());
    }
}
