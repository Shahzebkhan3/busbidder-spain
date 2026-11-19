"""Tkinter interface for searching, comparing, and booking bus offers."""

from datetime import date
from decimal import Decimal, InvalidOperation
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .booking import BookingError, BookingStore
from .filtering import filter_offers
from .models import Offer, TravelRequest
from .ranking import DEPARTURE_CHOICES, RankedOffer, ScoreWeights, rank_offers


DEPARTURE_LABELS = {"Any time": "any"}
DEPARTURE_LABELS.update({choice.title(): choice for choice in DEPARTURE_CHOICES if choice != "any"})


def _date_input(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"Enter {label} as YYYY-MM-DD.") from error


def _number_input(value: str, label: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except InvalidOperation as error:
        raise ValueError(f"Enter a number for {label}.") from error


class SearchWindow:
    """Show the existing search, ranking and booking functions in one window."""

    def __init__(
        self, root: tk.Tk, bookings: BookingStore, destinations: list[str], offers: list[Offer]
    ) -> None:
        self.root = root
        self.bookings = bookings
        self.destinations = destinations
        self.ranked: dict[str, RankedOffer] = {}
        self.results_current = False
        default_destination = offers[0].destination if offers else destinations[0]
        dates = [
            offer.departs_at.date() for offer in offers if offer.destination == default_destination
        ]
        self.destination = tk.StringVar(root, value=default_destination)
        self.first_date = tk.StringVar(root, value=min(dates).isoformat() if dates else "")
        self.last_date = tk.StringVar(root, value=max(dates).isoformat() if dates else "")
        self.budget = tk.StringVar(root)
        self.transfers = tk.StringVar(root)
        self.changeable = tk.BooleanVar(root, value=False)
        self.departure = tk.StringVar(root, value="Any time")
        self.weights = {
            name: tk.StringVar(root, value=str(value))
            for name, value in ScoreWeights().as_dict().items()
        }
        self.status = tk.StringVar(root, value="Set your requirements and select Search offers.")
        self.recommendation = tk.StringVar(root)
        self.details = tk.StringVar(root)

        self._build_window()
        for field in (
            self.destination, self.first_date, self.last_date, self.budget,
            self.transfers, self.changeable, self.departure, *self.weights.values(),
        ):
            field.trace_add("write", self._request_changed)

    def _build_window(self) -> None:
        self.root.title("BusBidder Spain")
        width = min(1160, self.root.winfo_screenwidth() - 40)
        height = min(720, self.root.winfo_screenheight() - 72)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(980, width), min(640, height))

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#F2F5F8")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("TLabel", background="#FFFFFF", foreground="#1C2D40", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground="#4B6077")
        style.configure("Error.TLabel", foreground="#9E3126")
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("TCheckbutton", background="#FFFFFF", foreground="#1C2D40", font=("Segoe UI", 10))
        style.configure("Header.TFrame", background="#172E45")
        style.configure(
            "Title.TLabel", background="#172E45", foreground="#FFFFFF", font=("Segoe UI", 21, "bold"),
        )
        style.configure(
            "Route.TLabel", background="#172E45", foreground="#D9E6F1", font=("Segoe UI", 11),
        )
        style.configure("Primary.TButton", background="#126B62", foreground="#FFFFFF", padding=(12, 8))
        style.map(
            "Primary.TButton",
            background=[("disabled", "#DCE4EA"), ("active", "#0C544B")],
            foreground=[("disabled", "#4B6077")],
        )
        style.configure("TEntry", padding=4)
        style.configure("TCombobox", padding=4)
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 10), background="#FFFFFF")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#E5EEF5")
        style.map("Treeview", background=[("selected", "#D3EDE9")], foreground=[("selected", "#112D2A")])
        style.configure("TNotebook.Tab", padding=(12, 5))

        header = ttk.Frame(self.root, padding=(22, 12), style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="BusBidder Spain", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Departures from Madrid", style="Route.TLabel").pack(side="right")

        body = ttk.Frame(self.root, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        form = ttk.Frame(body, padding=16, style="Card.TFrame")
        form.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        results = ttk.Frame(body, padding=16, style="Card.TFrame")
        results.grid(row=0, column=1, sticky="nsew")
        self._build_form(form)
        self._build_results(results)

    def _build_form(self, form: ttk.Frame) -> None:
        ttk.Label(form, text="Trip requirements", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(form, text="Destination").pack(anchor="w")
        ttk.Combobox(
            form, textvariable=self.destination, values=self.destinations, state="readonly", width=28,
        ).pack(fill="x", pady=(2, 8))
        date_fields = ttk.Frame(form, style="Card.TFrame")
        date_fields.pack(fill="x", pady=(0, 6))
        self._entry(date_fields, 0, "Earliest departure", self.first_date, 13)
        self._entry(date_fields, 1, "Latest departure", self.last_date, 13)
        ttk.Label(form, text="Dates use YYYY-MM-DD", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))

        limits = ttk.Frame(form, style="Card.TFrame")
        limits.pack(fill="x")
        self._entry(limits, 0, "Max. price (€)", self.budget, 13)
        self._entry(limits, 1, "Max. transfers", self.transfers, 13)
        ttk.Label(form, text="Leave limits blank for no limit", style="Muted.TLabel").pack(anchor="w", pady=(4, 4))
        ttk.Checkbutton(form, text="Require a changeable ticket", variable=self.changeable).pack(anchor="w")

        ttk.Separator(form).pack(fill="x", pady=12)
        ttk.Label(form, text="Scoring preferences", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(form, text="Preferred departure").pack(anchor="w")
        ttk.Combobox(
            form, textvariable=self.departure, values=list(DEPARTURE_LABELS), state="readonly",
        ).pack(fill="x", pady=(2, 8))
        ttk.Label(form, text="Weights (%) — total must be 100", style="Muted.TLabel").pack(anchor="w")
        weights = ttk.Frame(form, style="Card.TFrame")
        weights.pack(fill="x", pady=(4, 12))
        for column, (name, value) in enumerate(self.weights.items()):
            self._entry(weights, column, name.title(), value, 6)
        ttk.Button(form, text="Search offers", command=self.search, style="Primary.TButton").pack(fill="x")

    @staticmethod
    def _entry(parent: ttk.Frame, column: int, label: str, field: tk.StringVar, width: int) -> None:
        parent.columnconfigure(column, weight=1)
        ttk.Label(parent, text=label).grid(row=0, column=column, sticky="w", padx=(0, 6))
        ttk.Entry(parent, textvariable=field, width=width).grid(
            row=1, column=column, sticky="ew", padx=(0, 6), pady=(2, 0),
        )

    def _build_results(self, results: ttk.Frame) -> None:
        ttk.Label(results, text="Search results", style="Section.TLabel").pack(anchor="w")
        self.status_label = ttk.Label(results, textvariable=self.status, style="Muted.TLabel", wraplength=540)
        self.status_label.pack(anchor="w", pady=(4, 10))

        self.tabs = ttk.Notebook(results)
        self.tabs.pack(fill="both", expand=True)
        self.offers_tab = ttk.Frame(self.tabs, style="Card.TFrame")
        rejected_tab = ttk.Frame(self.tabs, style="Card.TFrame")
        self.tabs.add(self.offers_tab, text="Ranked offers")
        self.tabs.add(rejected_tab, text="Rejected (0)")

        columns = (
            ("rank", "Rank", 40), ("company", "Company", 118), ("departure", "Departure", 120),
            ("price", "Fare", 67), ("duration", "Minutes", 56), ("seats", "Seats", 45), ("score", "Score / 100", 76),
        )
        table = ttk.Frame(self.offers_tab, style="Card.TFrame")
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            table, columns=[name for name, _, _ in columns], show="headings", selectmode="browse", height=6,
        )
        for name, heading, width in columns:
            anchor = "w" if name in ("company", "departure") else "center"
            self.tree.heading(name, text=heading, anchor=anchor)
            self.tree.column(name, width=width, minwidth=width, anchor=anchor)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        scroll.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("alternate", background="#F2F7FA")
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        self.recommendation_label = ttk.Label(
            self.offers_tab, textvariable=self.recommendation, wraplength=540, padding=(8, 8),
        )
        self.recommendation_label.pack(fill="x")
        self.details_label = ttk.Label(
            self.offers_tab, textvariable=self.details, style="Muted.TLabel", wraplength=540, padding=(8, 2),
        )
        self.details_label.pack(fill="x")
        self.book_button = ttk.Button(
            self.offers_tab, text="Book selected offer", command=self.book_selected, style="Primary.TButton",
        )
        self.book_button.pack(anchor="e", pady=8, padx=8)
        self.book_button.state(["disabled"])
        results.bind("<Configure>", self._wrap_labels)

        self.rejected_text = tk.Text(
            rejected_tab, width=40, height=10, wrap="word", padx=12, pady=12,
            state="disabled", bg="#FFFFFF", fg="#1C2D40", font=("Segoe UI", 10), relief="flat",
        )
        rejected_scroll = ttk.Scrollbar(rejected_tab, orient="vertical", command=self.rejected_text.yview)
        self.rejected_text.configure(yscrollcommand=rejected_scroll.set)
        rejected_scroll.pack(side="right", fill="y")
        self.rejected_text.pack(fill="both", expand=True)

    def _wrap_labels(self, event: tk.Event) -> None:
        for label in (self.status_label, self.recommendation_label, self.details_label):
            label.configure(wraplength=max(300, event.width - 58))

    def _request_changed(self, *_args: str) -> None:
        if self.results_current:
            self.results_current = False
            self.book_button.state(["disabled"])
            self._show_status("Search again to apply your changes.")

    def _show_status(self, text: str, error: bool = False) -> None:
        self.status.set(text)
        self.status_label.configure(style="Error.TLabel" if error else "Muted.TLabel")

    def _clear_results(self) -> None:
        self.results_current = False
        self.ranked.clear()
        self.tree.delete(*self.tree.get_children())
        self.recommendation.set("")
        self.details.set("")
        self.book_button.state(["disabled"])
        self._show_rejected({})

    def _read_preferences(self) -> tuple[TravelRequest, ScoreWeights, str]:
        budget = self.budget.get().strip()
        transfers = self.transfers.get().strip()
        try:
            maximum_transfers = int(transfers) if transfers else None
        except ValueError as error:
            raise ValueError("Enter a whole number for maximum transfers.") from error
        request = TravelRequest(
            destination=self.destination.get(),
            first_departure_date=_date_input(self.first_date.get(), "the earliest departure"),
            last_departure_date=_date_input(self.last_date.get(), "the latest departure"),
            max_price_eur=_number_input(budget, "maximum price") if budget else None,
            max_transfers=maximum_transfers,
            require_changeable=self.changeable.get(),
        )
        weights = ScoreWeights(**{
            name: _number_input(field.get(), f"the {name} weight") for name, field in self.weights.items()
        })
        return request, weights, DEPARTURE_LABELS[self.departure.get()]

    def search(self) -> None:
        """Apply the trip requirements and show a fresh ranking."""
        self._clear_results()
        self.tabs.select(self.offers_tab)
        try:
            request, weights, departure = self._read_preferences()
            result = filter_offers(self.bookings.available_offers(), request)
            ranking = rank_offers(result.accepted, weights, departure)
        except ValueError as error:
            self._show_status(str(error), error=True)
            return

        self._show_rejected(result.rejected)
        if not ranking.offers:
            self._show_status("No offers matched. Check the Rejected tab or change your requirements.")
            return

        self.ranked = {row.offer.offer_id: row for row in ranking.offers}
        for position, row in enumerate(ranking.offers):
            offer = row.offer
            rank = f"={row.rank}" if row.tied else str(row.rank)
            self.tree.insert("", "end", iid=offer.offer_id, values=(
                rank, offer.company, offer.departs_at.strftime("%d %b %Y %H:%M"),
                f"€{offer.price_eur:.2f}", row.duration_minutes, offer.seats_available, f"{row.total:.1f}",
            ), tags=("alternate",) if position % 2 else ())

        self.results_current = True
        first = ranking.offers[0].offer.offer_id
        self.tree.selection_set(first)
        self.tree.focus(first)
        self._selection_changed()
        self.recommendation.set("\n".join([ranking.recommendation or "", *ranking.notes]))
        count = len(ranking.offers)
        self._show_status(f"{count} {'offer matches' if count == 1 else 'offers match'}. Select a row for details.")

    def _show_rejected(self, rejected: dict[str, list[str]]) -> None:
        self.tabs.tab(1, text=f"Rejected ({len(rejected)})")
        self.rejected_text.configure(state="normal")
        self.rejected_text.delete("1.0", "end")
        text = "\n\n".join(f"{offer_id} · {' '.join(reasons)}" for offer_id, reasons in rejected.items())
        self.rejected_text.insert("1.0", text or "No rejected offers to show.")
        self.rejected_text.configure(state="disabled")

    def _selected_offer(self) -> RankedOffer | None:
        selected = self.tree.selection()
        return self.ranked.get(selected[0]) if selected else None

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        row = self._selected_offer()
        self.book_button.state(["!disabled"] if self.results_current and row else ["disabled"])
        if row is None:
            self.details.set("")
            return
        offer = row.offer
        scores = "   ".join(f"{name.title()} {value:.1f}" for name, value in row.scores.items())
        self.details.set(
            f"{offer.offer_id} · Arrives {offer.arrives_at:%d %b %Y %H:%M} · Transfers {offer.transfers}\n"
            f"Changeable: {'Yes' if offer.changeable else 'No'} · Refundable: {'Yes' if offer.refundable else 'No'}\n"
            f"Scores out of 100 · {scores}"
        )

    def book_selected(self) -> None:
        """Confirm the selected fare, save one seat, then refresh availability."""
        row = self._selected_offer()
        if not self.results_current or row is None:
            return
        offer = row.offer
        confirmed = messagebox.askyesno(
            "Confirm simulated booking",
            f"Book one seat with {offer.company} ({offer.offer_id}) for €{offer.price_eur:.2f}?\n"
            f"Madrid to {offer.destination} · {offer.departs_at:%d %b %Y %H:%M}",
            parent=self.root,
        )
        if not confirmed:
            return
        try:
            booking = self.bookings.confirm_booking(offer.offer_id)
        except BookingError as error:
            self.search()
            messagebox.showerror("Booking unavailable", str(error), parent=self.root)
            return

        self.search()
        messagebox.showinfo(
            "Booking confirmed",
            f"One seat booked on {booking.offer_id} with {booking.company}.\n"
            f"Reference: {booking.reference}",
            parent=self.root,
        )


def launch(bookings: BookingStore, destinations: list[str], offers: list[Offer]) -> int:
    """Open the search window and wait for it to close."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Could not open the BusBidder window: {error}", file=sys.stderr)
        return 1
    SearchWindow(root, bookings, destinations, offers)
    root.mainloop()
    return 0
