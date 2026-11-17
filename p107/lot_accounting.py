"""FIFO lots and quantity-matched wash deferrals for a closed stock-only account.

Matching covers the same ticker and side, including ordinary rebalances and
temporary-security sales. Long/short overlap, options and household activity
are excluded from this research account. This is not broker tax reporting.
"""
from copy import deepcopy
from datetime import timedelta

EPS=1e-8


def held_more_than_year(opened,when,credit=0):
    effective=opened-timedelta(days=credit)
    try:anniversary=effective.replace(year=effective.year+1)
    except ValueError:anniversary=effective.replace(year=effective.year+1,day=28)
    return when>anniversary


class LotBook:
    def __init__(self):
        self.lots=[]
        self.realizations=[]
        self.pending=[]
        self.matches=[]
        self.next_id=1

    def holdings(self,ticker,side):
        return [l for l in self.lots if l['ticker']==ticker and l['side']==side and l['qty']>EPS]

    def quantity(self,ticker,side):
        return sum(l['qty'] for l in self.holdings(ticker,side))

    def _new_id(self):
        value=self.next_id;self.next_id+=1;return value

    def _piece(self,lot,qty):
        if qty>=lot['qty']-EPS:return lot
        part=deepcopy(lot);part['id']=self._new_id();part['qty']=qty
        lot['qty']-=qty
        self.lots.insert(self.lots.index(lot),part)
        return part

    def _match(self,pending,lot,when):
        qty=min(pending['qty'],lot['qty'])
        if qty<EPS:return
        lot=self._piece(lot,qty)
        loss=qty*pending['loss_per_share']
        direction=1 if lot['side']=='long' else -1
        lot['tax_basis']+=direction*pending['loss_per_share']
        lot['holding_credit']+=pending['held_days'] if lot['side']=='long' else 0
        lot['wash_used']=True
        pending['record']['tax_pnl']+=loss
        pending['record']['wash_disallowed']+=loss
        pending['qty']-=qty
        self.matches.append(dict(sale_date=pending['date'].isoformat(),
                                 replacement_date=lot['opened'].isoformat(),
                                 matched_on=when.isoformat(),ticker=lot['ticker'],
                                 side=lot['side'],shares=qty,loss_deferred=loss,
                                 replacement_lot_id=lot['id']))

    def open(self,ticker,side,qty,price,when,fee_per_share=0.):
        self.pending=[p for p in self.pending if p['qty']>EPS and (when-p['date']).days<=30]
        sign=1 if side=='long' else -1
        lot=dict(id=self._new_id(),ticker=ticker,side=side,qty=qty,
                 economic_basis=price,tax_basis=price+sign*fee_per_share,
                 opened=when,holding_credit=0,wash_used=False,in_lieu=0.)
        self.lots.append(lot)
        remaining=lot
        for pending in self.pending:
            if (pending['qty']>EPS and pending['ticker']==ticker and pending['side']==side
                    and 0<=(when-pending['date']).days<=30 and remaining['qty']>EPS):
                self._match(pending,remaining,when)
                # A fully matched lot cannot be assigned to another loss. A
                # partial match leaves the unmatched original segment in place.
                if remaining['wash_used']:break
        return lot

    def close(self,ticker,side,qty,price,when,reason,fee_per_share=0.,lot_order=None):
        if qty>self.quantity(ticker,side)+1e-6:raise ValueError('Sale exceeds available shares')
        holdings=list(self.holdings(ticker,side))
        if lot_order is not None:
            if not isinstance(lot_order,(list,tuple)) or any(type(i) is not int for i in lot_order):
                raise ValueError('Lot order must contain integer lot identifiers')
            by_id={lot['id']:lot for lot in holdings}
            if len(set(lot_order))!=len(lot_order) or any(i not in by_id for i in lot_order):
                raise ValueError('Lot order must identify distinct currently held lots')
            ordered=set(lot_order)
            holdings=[by_id[i] for i in lot_order]+[lot for lot in holdings if lot['id'] not in ordered]
        remaining=qty;created=[]
        for lot in holdings:
            if remaining<=EPS:break
            take=min(remaining,lot['qty']);sign=1 if side=='long' else -1
            economic=take*(price-lot['economic_basis'])*sign
            tax=take*((price-lot['tax_basis'])*sign-fee_per_share)
            age=(when-lot['opened']).days+lot['holding_credit']
            if side=='short' and (when-lot['opened']).days<=45:
                tax-=take*lot['in_lieu']
            character='lt' if side=='long' and (lot.get('inherited') or held_more_than_year(lot['opened'],when,lot['holding_credit'])) else 'st'
            if side=='long' and 'gift_fmv' in lot:
                tax=take*gift_sale_gain(lot['tax_basis'],lot['gift_fmv'],price-fee_per_share)
                if tax<0 and lot['gift_fmv']<lot['tax_basis']:character='st'
            record=dict(date=when.isoformat(),year=when.year,ticker=ticker,side=side,
                        lot_id=lot['id'],shares=take,economic_pnl=economic,tax_pnl=tax,
                        character=character,wash_disallowed=0.,reason=reason)
            self.realizations.append(record);created.append((record,age,tax/take))
            lot['qty']-=take;remaining-=take
        self.lots=[l for l in self.lots if l['qty']>EPS]
        # Match only shares still held after this complete sale order. Recently
        # acquired shares sold in the same order are not retained replacements.
        for record,age,per_share in created:
            if per_share>=-EPS:continue
            pending=dict(date=when,ticker=ticker,side=side,qty=record['shares'],
                         loss_per_share=-per_share,held_days=age,record=record)
            for lot in list(self.holdings(ticker,side)):
                if pending['qty']<=EPS:break
                if not lot['wash_used'] and 0<=(when-lot['opened']).days<=30:
                    self._match(pending,lot,when)
            if pending['qty']>EPS:self.pending.append(pending)
        return [record for record,_,_ in created]

    def split(self,ticker,factor):
        for lot in self.lots:
            if lot['ticker']==ticker:
                lot['qty']*=factor
                for key in ('economic_basis','tax_basis','in_lieu'):lot[key]/=factor
        for p in self.pending:
            if p['ticker']==ticker:
                p['qty']*=factor;p['loss_per_share']/=factor

    def in_lieu(self,ticker,amount):
        for lot in self.holdings(ticker,'short'):lot['in_lieu']+=amount

    def economic_embedded(self,prices):
        return sum(l['qty']*(prices[l['ticker']]-l['economic_basis'])*(1 if l['side']=='long' else -1)
                   for l in self.lots)

    def tax_embedded(self,prices):
        return sum(l['qty']*(prices[l['ticker']]-l['tax_basis'])*(1 if l['side']=='long' else -1)
                   for l in self.lots)

    def buckets(self,year):
        answer=dict(gain_st=0.,gain_lt=0.,loss_st=0.,loss_lt=0.)
        for record in self.realizations:
            if record['year']==year:
                pnl=record['tax_pnl'];answer[('gain_' if pnl>=0 else 'loss_')+record['character']]+=abs(pnl)
        return answer

    def pending_after(self,when):
        return [p for p in self.pending if p['qty']>EPS and 0<=(when-p['date']).days<=30]


def gift_sale_gain(donor_basis,fmv_at_gift,sale_price):
    """Per-share dual basis; a sale inside the basis interval has zero gain/loss."""
    loss_basis=min(donor_basis,fmv_at_gift)
    if sale_price>donor_basis:return sale_price-donor_basis
    if sale_price<loss_basis:return sale_price-loss_basis
    return 0.
