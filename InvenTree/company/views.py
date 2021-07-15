"""
Django views for interacting with Company app
"""


# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, ListView

from django.urls import reverse
from django.forms import HiddenInput
from django.core.files.base import ContentFile

from moneyed import CURRENCIES

from PIL import Image
import requests
import io

from InvenTree.views import AjaxCreateView, AjaxUpdateView, AjaxDeleteView
from InvenTree.helpers import str2bool
from InvenTree.views import InvenTreeRoleMixin

from .models import Company
from .models import ManufacturerPart
from .models import SupplierPart

from part.models import Part

from .forms import EditSupplierPartForm
from .forms import CompanyImageDownloadForm

import common.models
import common.settings


class CompanyIndex(InvenTreeRoleMixin, ListView):
    """ View for displaying list of companies
    """

    model = Company
    template_name = 'company/index.html'
    context_object_name = 'companies'
    paginate_by = 50
    permission_required = 'company.view_company'

    def get_context_data(self, **kwargs):

        ctx = super().get_context_data(**kwargs)

        # Provide custom context data to the template,
        # based on the URL we use to access this page

        lookup = {
            reverse('supplier-index'): {
                'title': _('Suppliers'),
                'button_text': _('New Supplier'),
                'filters': {'is_supplier': 'true'},
                'pagetype': 'suppliers',
            },
            reverse('manufacturer-index'): {
                'title': _('Manufacturers'),
                'button_text': _('New Manufacturer'),
                'filters': {'is_manufacturer': 'true'},
                'pagetype': 'manufacturers',
            },
            reverse('customer-index'): {
                'title': _('Customers'),
                'button_text': _('New Customer'),
                'filters': {'is_customer': 'true'},
                'pagetype': 'customers',
            }
        }

        default = {
            'title': _('Companies'),
            'button_text': _('New Company'),
            'filters': {},
            'pagetype': 'companies'
        }

        context = None

        for item in lookup:
            if self.request.path == item:
                context = lookup[item]
                break

        if context is None:
            context = default

        for key, value in context.items():
            ctx[key] = value

        return ctx

    def get_queryset(self):
        """ Retrieve the Company queryset based on HTTP request parameters.

        - supplier: Filter by supplier
        - customer: Filter by customer
        """
        queryset = Company.objects.all().order_by('name')

        if self.request.GET.get('supplier', None):
            queryset = queryset.filter(is_supplier=True)

        if self.request.GET.get('customer', None):
            queryset = queryset.filter(is_customer=True)

        return queryset


class CompanyDetail(DetailView):
    """ Detail view for Company object """
    context_obect_name = 'company'
    template_name = 'company/detail.html'
    queryset = Company.objects.all()
    model = Company
    permission_required = 'company.view_company'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        return ctx


class CompanyImageDownloadFromURL(AjaxUpdateView):
    """
    View for downloading an image from a provided URL
    """

    model = Company
    ajax_template_name = 'image_download.html'
    form_class = CompanyImageDownloadForm
    ajax_form_title = _('Download Image')

    def validate(self, company, form):
        """
        Validate that the image data are correct
        """
        # First ensure that the normal validation routines pass
        if not form.is_valid():
            return

        # We can now extract a valid URL from the form data
        url = form.cleaned_data.get('url', None)

        # Download the file
        response = requests.get(url, stream=True)

        # Look at response header, reject if too large
        content_length = response.headers.get('Content-Length', '0')

        try:
            content_length = int(content_length)
        except (ValueError):
            # If we cannot extract meaningful length, just assume it's "small enough"
            content_length = 0

        # TODO: Factor this out into a configurable setting
        MAX_IMG_LENGTH = 10 * 1024 * 1024

        if content_length > MAX_IMG_LENGTH:
            form.add_error('url', _('Image size exceeds maximum allowable size for download'))
            return

        self.response = response

        # Check for valid response code
        if not response.status_code == 200:
            form.add_error('url', _('Invalid response: {code}').format(code=response.status_code))
            return

        response.raw.decode_content = True

        try:
            self.image = Image.open(response.raw).convert()
            self.image.verify()
        except:
            form.add_error('url', _("Supplied URL is not a valid image file"))
            return

    def save(self, company, form, **kwargs):
        """
        Save the downloaded image to the company
        """
        fmt = self.image.format

        if not fmt:
            fmt = 'PNG'

        buffer = io.BytesIO()

        self.image.save(buffer, format=fmt)

        # Construct a simplified name for the image
        filename = f"company_{company.pk}_image.{fmt.lower()}"

        company.image.save(
            filename,
            ContentFile(buffer.getvalue()),
        )


class ManufacturerPartDetail(DetailView):
    """ Detail view for ManufacturerPart """
    model = ManufacturerPart
    template_name = 'company/manufacturer_part_detail.html'
    context_object_name = 'part'
    queryset = ManufacturerPart.objects.all()
    permission_required = 'purchase_order.view'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        return ctx


class SupplierPartDetail(DetailView):
    """ Detail view for SupplierPart """
    model = SupplierPart
    template_name = 'company/supplier_part_detail.html'
    context_object_name = 'part'
    queryset = SupplierPart.objects.all()
    permission_required = 'purchase_order.view'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        return ctx


class SupplierPartEdit(AjaxUpdateView):
    """ Update view for editing SupplierPart """

    model = SupplierPart
    context_object_name = 'part'
    form_class = EditSupplierPartForm
    ajax_template_name = 'modal_form.html'
    ajax_form_title = _('Edit Supplier Part')

    def save(self, supplier_part, form, **kwargs):
        """ Process ManufacturerPart data """

        manufacturer = form.cleaned_data.get('manufacturer', None)
        MPN = form.cleaned_data.get('MPN', None)
        kwargs = {'manufacturer': manufacturer,
                  'MPN': MPN,
                  }
        supplier_part.save(**kwargs)

    def get_form(self):
        form = super().get_form()

        supplier_part = self.get_object()

        # Hide Manufacturer fields
        form.fields['manufacturer'].widget = HiddenInput()
        form.fields['MPN'].widget = HiddenInput()

        # It appears that hiding a MoneyField fails validation
        # Therefore the idea to set the value before hiding
        if form.is_valid():
            form.cleaned_data['single_pricing'] = supplier_part.unit_pricing
        # Hide the single-pricing field (only for creating a new SupplierPart!)
        form.fields['single_pricing'].widget = HiddenInput()

        return form

    def get_initial(self):
        """ Fetch data from ManufacturerPart """

        initials = super(SupplierPartEdit, self).get_initial().copy()

        supplier_part = self.get_object()

        if supplier_part.manufacturer_part:
            if supplier_part.manufacturer_part.manufacturer:
                initials['manufacturer'] = supplier_part.manufacturer_part.manufacturer.id
            initials['MPN'] = supplier_part.manufacturer_part.MPN

        return initials


class SupplierPartCreate(AjaxCreateView):
    """ Create view for making new SupplierPart """

    model = SupplierPart
    form_class = EditSupplierPartForm
    ajax_template_name = 'company/supplier_part_create.html'
    ajax_form_title = _('Create new Supplier Part')
    context_object_name = 'part'

    def validate(self, part, form):

        single_pricing = form.cleaned_data.get('single_pricing', None)

        if single_pricing:
            # TODO - What validation steps can be performed on the single_pricing field?
            pass

    def get_context_data(self):
        """
        Supply context data to the form
        """

        ctx = super().get_context_data()

        # Add 'part' object
        form = self.get_form()

        part = form['part'].value()

        try:
            part = Part.objects.get(pk=part)
        except (ValueError, Part.DoesNotExist):
            part = None

        ctx['part'] = part

        return ctx

    def save(self, form):
        """
        If single_pricing is defined, add a price break for quantity=1
        """

        # Save the supplier part object
        supplier_part = super().save(form)

        # Process manufacturer data
        manufacturer = form.cleaned_data.get('manufacturer', None)
        MPN = form.cleaned_data.get('MPN', None)
        kwargs = {'manufacturer': manufacturer,
                  'MPN': MPN,
                  }
        supplier_part.save(**kwargs)

        single_pricing = form.cleaned_data.get('single_pricing', None)

        if single_pricing:

            supplier_part.add_price_break(1, single_pricing)

        return supplier_part

    def get_form(self):
        """ Create Form instance to create a new SupplierPart object.
        Hide some fields if they are not appropriate in context
        """
        form = super(AjaxCreateView, self).get_form()

        if form.initial.get('part', None):
            # Hide the part field
            form.fields['part'].widget = HiddenInput()

        if form.initial.get('manufacturer', None):
            # Hide the manufacturer field
            form.fields['manufacturer'].widget = HiddenInput()
            # Hide the MPN field
            form.fields['MPN'].widget = HiddenInput()

        return form

    def get_initial(self):
        """ Provide initial data for new SupplierPart:

        - If 'supplier_id' provided, pre-fill supplier field
        - If 'part_id' provided, pre-fill part field
        """
        initials = super(SupplierPartCreate, self).get_initial().copy()

        manufacturer_id = self.get_param('manufacturer')
        supplier_id = self.get_param('supplier')
        part_id = self.get_param('part')
        manufacturer_part_id = self.get_param('manufacturer_part')

        supplier = None

        if supplier_id:
            try:
                supplier = Company.objects.get(pk=supplier_id)
                initials['supplier'] = supplier
            except (ValueError, Company.DoesNotExist):
                supplier = None

        if manufacturer_id:
            try:
                initials['manufacturer'] = Company.objects.get(pk=manufacturer_id)
            except (ValueError, Company.DoesNotExist):
                pass

        if manufacturer_part_id:
            try:
                # Get ManufacturerPart instance information
                manufacturer_part_obj = ManufacturerPart.objects.get(pk=manufacturer_part_id)
                initials['part'] = Part.objects.get(pk=manufacturer_part_obj.part.id)
                initials['manufacturer'] = manufacturer_part_obj.manufacturer.id
                initials['MPN'] = manufacturer_part_obj.MPN
            except (ValueError, ManufacturerPart.DoesNotExist, Part.DoesNotExist, Company.DoesNotExist):
                pass

        if part_id:
            try:
                initials['part'] = Part.objects.get(pk=part_id)
            except (ValueError, Part.DoesNotExist):
                pass

        # Initial value for single pricing
        if supplier:
            currency_code = supplier.currency_code
        else:
            currency_code = common.settings.currency_code_default()

        currency = CURRENCIES.get(currency_code, None)

        if currency_code:
            initials['single_pricing'] = ('', currency)

        return initials


class SupplierPartDelete(AjaxDeleteView):
    """ Delete view for removing a SupplierPart.

    SupplierParts can be deleted using a variety of 'selectors'.

    - ?part=<pk> -> Delete a single SupplierPart object
    - ?parts=[] -> Delete a list of SupplierPart objects

    """

    success_url = '/supplier/'
    ajax_template_name = 'company/supplier_part_delete.html'
    ajax_form_title = _('Delete Supplier Part')

    role_required = 'purchase_order.delete'

    parts = []

    def get_context_data(self):
        ctx = {}

        ctx['parts'] = self.parts

        return ctx

    def get_parts(self):
        """ Determine which SupplierPart object(s) the user wishes to delete.
        """

        self.parts = []

        # User passes a single SupplierPart ID
        if 'part' in self.request.GET:
            try:
                self.parts.append(SupplierPart.objects.get(pk=self.request.GET.get('part')))
            except (ValueError, SupplierPart.DoesNotExist):
                pass

        elif 'parts[]' in self.request.GET:

            part_id_list = self.request.GET.getlist('parts[]')

            self.parts = SupplierPart.objects.filter(id__in=part_id_list)

    def get(self, request, *args, **kwargs):
        self.request = request
        self.get_parts()

        return self.renderJsonResponse(request, form=self.get_form())

    def post(self, request, *args, **kwargs):
        """ Handle the POST action for deleting supplier parts.
        """

        self.request = request
        self.parts = []

        for item in self.request.POST:
            if item.startswith('supplier-part-'):
                pk = item.replace('supplier-part-', '')

                try:
                    self.parts.append(SupplierPart.objects.get(pk=pk))
                except (ValueError, SupplierPart.DoesNotExist):
                    pass

        confirm = str2bool(self.request.POST.get('confirm_delete', False))

        data = {
            'form_valid': confirm,
        }

        if confirm:
            for part in self.parts:
                part.delete()

        return self.renderJsonResponse(self.request, data=data, form=self.get_form())
